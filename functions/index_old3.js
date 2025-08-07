// index.js
const functions = require('firebase-functions');
const express = require('express');
const axios = require('axios');
const { KendraClient, QueryCommand } = require("@aws-sdk/client-kendra");

const app = express();
app.use(express.json());

// Firebase Functions に設定済みのAWS認証情報を取得
const awsConfig = functions.config().aws; // 例: aws.access_key_id, aws.secret_access_key

// AWS Kendra Client (SDK v3)
const kendraClient = new KendraClient({
  region: 'us-east-1',
  credentials: {
    accessKeyId: awsConfig.aws_access_key_id,
    secretAccessKey: awsConfig.aws_secret_access_key,
  },
});

// 各種定数（環境変数から取得）
const SLACK_BOT_TOKEN = functions.config().slack.token;
const OPENAI_API_KEY = functions.config().openai.key;
const GPT_MODEL = 'ft:gpt-4o-2024-08-06:techfund-inc::B5TwK9je';
const KENDRA_INDEX_ID = 'afb73f09-d365-439d-8a02-bd156d9ba524';
// BotのユーザーID（ループ防止・メンションチェック用）
const BOT_USER_ID = '<@U0639A0LJBV>';

app.post('/slack/events', async (req, res) => {
  console.log("access");

  // リトライリクエストを検出して無視する
  if (req.headers['x-slack-retry-num']) {
    console.log('X-Slack-Retry-Num header detected, ignoring retry request:', req.headers['x-slack-retry-num']);
    return res.status(200).send();
  }

  // Slack URL検証リクエスト対応
  if (req.body.type === 'url_verification') {
    return res.status(200).send(req.body.challenge);
  }
  
  const event = req.body.event;
  // Botからのメッセージは無視（ループ防止）
  if (event.bot_id) {
    console.log('Botからのメッセージのため無視します。');
    return res.status(200).send();
  }
  // BotのユーザーIDがメンションされていない場合は無視
  if (!event.text || !event.text.includes(BOT_USER_ID)) {
    console.log('BotユーザーIDがメンションされていないため無視します。');
    return res.status(200).send();
  }
  
  console.log("event.type", event.type);
  if (event && (event.type === 'app_mention' || event.type === 'message')) {
    try {
      // Botへのメンション部分を除去して質問文を取得
      const text = event.text.replace(new RegExp(BOT_USER_ID, 'g'), '').trim();
      console.log("text ", JSON.stringify(text));

      // ① Kendraに問い合わせ
      const kendraData = await queryKendra(text);

      // ② システムメッセージにKendra情報と「まっつんらしい考え方や口調で回答してください。」を追加してGPTへ問い合わせ
      const systemMessage = `メンバーから質問のメッセージが送られてきます。下記に記載する「関連するNotionページ情報」も参考にしつつ、まっつんらしい考え方や口調でメンバーからの質問に回答してください。\n【関連するNotionページ情報】\n${kendraData.vector}`;
      console.log("systemMessage ", JSON.stringify(systemMessage));

      const reply = await queryGPT(systemMessage, text);
      const replyText = `${reply}\n\n【関連Notion情報】\n${kendraData.meta}`
      console.log("reply ", JSON.stringify(replyText));

      // ③ Slackへスレッド返信
      await postSlackMessage(event.channel, replyText, event.ts);
      return res.status(200).send();
    } catch (err) {
      console.error(err);
      return res.status(500).send('Internal Server Error');
    }
  }
  return res.status(200).send();
});

// AWS Kendraへ問い合わせる関数（SDK v3 使用）
async function queryKendra(queryText) {
  const params = {
    IndexId: KENDRA_INDEX_ID,
    QueryText: queryText,
    PageContentFormatter: "HTML"  // ここで page_content_formatter を指定
  };

  try {
    const command = new QueryCommand(params);
    const response = await kendraClient.send(command);

    console.log("kendraData ", JSON.stringify(response.ResultItems));

    const vector = response.ResultItems.map(item => {
      const title = item.DocumentTitle && item.DocumentTitle.Text ? item.DocumentTitle.Text : 'No Title';
      const excerpt = item.DocumentExcerpt && item.DocumentExcerpt.Text ? item.DocumentExcerpt.Text : '';
      return `${title}\n${excerpt}\n\n`;
    }).join('\n');

    const meta = response.ResultItems.map(item => {
      const title = item.DocumentTitle && item.DocumentTitle.Text ? item.DocumentTitle.Text : 'No Title';
      const excerpt = item.DocumentExcerpt && item.DocumentExcerpt.Text ? item.DocumentExcerpt.Text : '';
      const uri = item.DocumentURI && item.DocumentURI.trim() ? item.DocumentURI.trim() : '';
      if (uri) {
        return `・<${uri}|${title}>`;
      } else {
        return `・${title}`;
      }
    }).join('\n');

    return {"vector": vector, "meta": meta};
  } catch (error) {
    console.error('Kendra query error:', error);
    return 'Kendra情報の取得に失敗しました。';
  }
}

// OpenAI GPT-4oへ問い合わせる関数
async function queryGPT(systemMessage, userMessage) {
  const messages = [
    { role: 'system', content: systemMessage },
    { role: 'user', content: userMessage },
  ];

  try {
    const response = await axios.post('https://api.openai.com/v1/chat/completions', {
      model: GPT_MODEL,
      messages: messages,
    }, {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${OPENAI_API_KEY}`,
      },
    });
    return response.data.choices[0].message.content.trim();
  } catch (error) {
    console.error('OpenAI API error:', error.response?.data || error);
    return '回答の生成に失敗しました。';
  }
}

// Slackにメッセージ投稿する関数
async function postSlackMessage(channel, text, thread_ts) {
  try {
    await axios.post('https://slack.com/api/chat.postMessage', {
      channel: channel,
      text: text,
      thread_ts: thread_ts,
    }, {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${SLACK_BOT_TOKEN}`,
      },
    });
  } catch (error) {
    console.error('Slack API error:', error.response?.data || error);
    throw error;
  }
}

exports.slackBot = functions.https.onRequest(app);