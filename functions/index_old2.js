const functions = require('firebase-functions');
const express = require('express');
const bodyParser = require('body-parser');
const crypto = require('crypto');
const axios = require('axios');
const aws4 = require('aws4');
const url = require('url');
const { WebClient } = require('@slack/web-api');

const app = express();

// rawBodyの保持（署名検証用）
app.use(bodyParser.json({
  verify: (req, res, buf) => {
    req.rawBody = buf.toString();
  }
}));

const SLACK_SIGNING_SECRET = functions.config().slack.signing_secret;
const SLACK_BOT_TOKEN = functions.config().slack.token;
const AWS_LAMBDA_ENDPOINT = functions.config().aws.lambda_endpoint;

const slackClient = new WebClient(SLACK_BOT_TOKEN);

// Slack署名の検証関数
function verifySlackRequest(req) {
  const signature = req.headers['x-slack-signature'];
  const timestamp = req.headers['x-slack-request-timestamp'];
  // タイムスタンプのチェック（5分以内）
  const fiveMinutesAgo = Math.floor(Date.now() / 1000) - (60 * 5);
  if (timestamp < fiveMinutesAgo) return false;

  const sigBasestring = `v0:${timestamp}:${req.rawBody}`;
  const mySignature = 'v0=' + crypto.createHmac('sha256', SLACK_SIGNING_SECRET)
    .update(sigBasestring, 'utf8')
    .digest('hex');

  return crypto.timingSafeEqual(Buffer.from(mySignature, 'utf8'), Buffer.from(signature, 'utf8'));
}

app.post('/slack/events', async (req, res) => {
  // Slack署名検証
  if (!verifySlackRequest(req)) {
    return res.status(400).send('Invalid signature');
  }

  const body = req.body;
  // URL検証リクエストの場合はchallenge値をそのまま返す
  if (body.type === 'url_verification' && body.challenge) {
    res.set('Content-Type', 'text/plain');
    return res.status(200).send(String(body.challenge).trim());
  }

  const event = body.event;
  if (event && event.type === 'message' && !event.subtype) {
    // botからのメッセージは無視（ループ防止）
    if (event.bot_id) {
      return res.status(200).send('OK');
    }
    // BotのユーザーID（<@U0639A0LJBV>）がメンションされているかチェック
    const botMention = '<@U0639A0LJBV>';
    if (!event.text || event.text.indexOf(botMention) === -1) {
      return res.status(200).send('OK');
    }

    const channel = event.channel;
    const userMessage = event.text;
    let promptForLambda = userMessage;
    // トリガーメッセージの場合、別のメッセージを取得
    const triggerMessage = `${botMention} どう思いますか？`;
    if (userMessage.trim() === triggerMessage) {
      try {
        const historyResponse = await slackClient.conversations.history({
          channel: channel,
          limit: 50,
        });
        const messagesHistory = historyResponse.messages;
        let targetMessage = null;
        for (const msg of messagesHistory) {
          if (msg.ts === event.ts) continue;
          if (msg.text && msg.text.indexOf('<@U03RHU7RP>') !== -1) {
            targetMessage = msg.text;
            break;
          }
        }
        if (targetMessage) {
          promptForLambda = targetMessage;
        }
      } catch (err) {
        console.error("Error fetching conversation history:", err);
        promptForLambda = userMessage;
      }
    }

    try {
      // AWS_IAM認証用の署名付きリクエスト作成
      const parsedUrl = url.parse(AWS_LAMBDA_ENDPOINT);
      const requestBody = JSON.stringify({ prompt: promptForLambda });
      const opts = {
        host: parsedUrl.host,
        path: parsedUrl.path,
        method: 'POST',
        body: requestBody,
        headers: {
          'Content-Type': 'application/json'
        }
      };
      aws4.sign(opts); // 署名を付与

      // 署名済みヘッダーでLambda Function URLにリクエスト
      const lambdaResponse = await axios({
         method: opts.method,
         url: AWS_LAMBDA_ENDPOINT,
         data: requestBody,
         headers: opts.headers
      });
      
      const answer = lambdaResponse.data.answer.trim();
      // Slackに返答を投稿
      await slackClient.chat.postMessage({
        channel: channel,
        text: answer,
      });
    } catch (error) {
      console.error('Error processing message:', error);
    }
  }
  return res.status(200).send('OK');
});

exports.slackBot = functions.https.onRequest(app);