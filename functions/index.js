// index.js
const functions = require('firebase-functions');
const express = require('express');
const axios = require('axios');
const { BedrockAgentRuntimeClient, RetrieveAndGenerateCommand } = require('@aws-sdk/client-bedrock-agent-runtime');

const app = express();
app.use(express.json());

const awsConfig = functions.config().aws;
// Firebase Functions用AWS認証情報とリージョン設定（functions.config()または環境変数から取得）
const awsRegion = functions.config().aws.region || "us-east-1";
const awsCreds = {
  accessKeyId: awsConfig.aws_access_key_id,
  secretAccessKey: awsConfig.aws_secret_access_key,
};

// Bedrock Agent Runtimeクライアントの初期化
const agentClient = new BedrockAgentRuntimeClient({
  region: awsRegion,
  credentials: awsCreds,
});

// ナレッジベースIDとモデルARN（RetrieveAndGenerateCommand用）
// ※MODEL_ARNは、Bedrockコンソールで提供されるFoundation Model ARNまたは推論プロファイルのARNを指定してください
const KNOWLEDGE_BASE_ID = "5T1BMLXOSU";
//const MODEL_ARN = "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-7-sonnet-20250219-v1:0";
const MODEL_ARN = "arn:aws:bedrock:us-east-1:039861401280:inference-profile/us.anthropic.claude-3-7-sonnet-20250219-v1:0";

// OpenAI GPT用定数
const OPENAI_API_KEY = functions.config().openai.key;
const GPT_4O_MODEL = "ft:gpt-4o-2024-08-06:techfund-inc::B5TwK9je";
const O3_MINI_MODEL = "o3-mini";

// Slack設定
const SLACK_BOT_TOKEN = functions.config().slack.token;
const BOT_USER_ID = "<@U0639A0LJBV>";
const BOT_USER_ID_RAW = "U0639A0LJBV";
const ALLOWED_USER_IDS = ["U03RHU7RP", "UMWUUDDT6test"];  // MTN:U03RHU7RP, MCH:UMWUUDDT6

// Slackイベントのエンドポイント
app.post('/slack/events', async (req, res) => {
  console.log("access");

  // リトライリクエスト検出（無視）
  if (req.headers['x-slack-retry-num']) {
    console.log('X-Slack-Retry-Num header detected, ignoring retry.');
    return res.status(200).send();
  }

  // Slack URL検証リクエスト対応
  if (req.body.type === 'url_verification') {
    return res.status(200).send(req.body.challenge);
  }

  const event = req.body.event;
  // Botからのメッセージは無視
  if (event.bot_id) {
    console.log('Botからのメッセージは無視。');
    return res.status(200).send();
  }
  // BotのユーザーIDがメンションされていない場合は無視
  if (!event.text || !event.text.includes(BOT_USER_ID)) {
    console.log('BotユーザーIDが含まれていないため無視。');
    return res.status(200).send();
  }

  // 許可済みユーザー以外のメンバーの場合は拒否返信して終了
  if (!ALLOWED_USER_IDS.includes(event.user)) {
    console.log('許可されたユーザー以外からのメッセージ');
    await postSlackMessage(event.channel, "許可されたユーザー以外にはお答えできません", event.ts);
    return res.status(200).send();
  }

  if (event && (event.type === 'app_mention' || event.type === 'message')) {
    try {
      // Botへのメンション部分を除去して質問文を抽出
      const question = event.text.replace(new RegExp(BOT_USER_ID, 'g'), '').trim();
      console.log("質問:", JSON.stringify(question));

      // ① Amazon Bedrock RetrieveAndGenerate APIで問い合わせ（ナレッジベース付きRAG回答取得）
      const { answer, citations } = await queryAmazonBedrock(question);
      const ragAnswer = answer || "RAG回答の取得に失敗しました。";

      // ② GPT-4oモデルに質問を5回問い合わせる（ユーザーメッセージは質問のみ）
      const systemMessage = "メンバーから質問のメッセージが送られてきます。まっつんらしい考え方や口調でメンバーからの質問に回答してください。";
      const gpt4oPromises = [];
      for (let i = 0; i < 5; i++) {
        gpt4oPromises.push(queryGPTGeneric(GPT_4O_MODEL, systemMessage, question));
      }
      const gpt4oResponses = await Promise.all(gpt4oPromises);
      console.log("まっつんモデルの回答:", JSON.stringify(gpt4oResponses));

      let messagesArray = [];
      // システムメッセージ（空で可）
      messagesArray.push({ role: "system", content: "" });
      if (event.thread_ts) {
        try {
          const threadMessages = await getThreadMessages(event.channel, event.thread_ts);
          // 時系列に並べ替え
          threadMessages.sort((a, b) => parseFloat(a.ts) - parseFloat(b.ts));
          threadMessages.forEach(message => {
            // 現在のメッセージ（最終指示用）は除外
            if (message.ts === event.ts) return;
            // bot自身の場合はassistant、それ以外はuserとして扱う
            const role = (message.user === BOT_USER_ID_RAW) ? "assistant" : "user";
            messagesArray.push({ role: role, content: message.text });
          });
        } catch (err) {
          console.error("スレッドメッセージ取得エラー:", err);
        }
      } else {
        // スレッドが無い場合は、最初のユーザーメッセージを追加
        messagesArray.push({ role: "user", content: question });
      }

      // ③ 最終指示のuserメッセージ作成（RAGの回答＋5つのAIモデルの回答を含む）
      let finalUserContent = "下記のRAGの回答を、下記5つのAIモデルの回答の口調に修正してください。回答は1つのみでお願いします。また、「検索の結果は」のような回答にはせず、過去のデータを引用したり記憶を思い出しているかのような口調にしてください。説明の中には記憶を辿るような内容は入れないでください。\n";
      finalUserContent += "# RAGの回答\n" + ragAnswer + "\n";
      finalUserContent += "# AIモデルの回答\n";
      gpt4oResponses.forEach((response, index) => {
        finalUserContent += `## ${index + 1}\n` + response + "\n";
      });
      messagesArray.push({ role: "user", content: finalUserContent });

      // ④ o3-miniへの問い合わせ（messages形式で送信）
      const finalReply = await queryGPTChat({ model: O3_MINI_MODEL, messages: messagesArray });

      // ⑤ 出典情報の整形（Slack用：箇条書き、リンク形式 <${uri}|${title}>）
      let slackCitationText = "";
      if (citations && Array.isArray(citations) && citations.length > 0) {
        const citationLinks = [];
        citations.forEach(citation => {
          if (citation.retrievedReferences && Array.isArray(citation.retrievedReferences)) {
            citation.retrievedReferences.forEach(ref => {
              const uri = ref.location?.kendraDocumentLocation?.uri || "";
              const title = ref.metadata?.["x-amz-kendra-document-title"] || "";
              if (uri && title) {
                citationLinks.push(`・<${uri}|${title}>`);
              }
            });
          }
        });
        slackCitationText = citationLinks.join("\n");
        console.log("slackCitationText", slackCitationText);
      }
      
      // ⑥ Slack返信メッセージの作成（o3-miniの最終回答に出典情報を付加）
      let slackReply = finalReply;
      if (slackCitationText) {
        slackReply += "\n\n【参考】\n" + slackCitationText;
      }

      // ⑦ Slackへスレッド返信
      await postSlackMessage(event.channel, slackReply, event.ts);
      return res.status(200).send();
    } catch (err) {
      console.error("エラー:", err);
      return res.status(500).send('Internal Server Error');
    }
  }
  return res.status(200).send();
});

// Amazon Bedrock RetrieveAndGenerate APIを使って問い合わせる関数
async function queryAmazonBedrock(queryText) {
  const input = {
    input: { text: queryText },
    retrieveAndGenerateConfiguration: {
      type: "KNOWLEDGE_BASE",
      knowledgeBaseConfiguration: {
        knowledgeBaseId: KNOWLEDGE_BASE_ID,
        modelArn: MODEL_ARN
      }
    }
  };

  const command = new RetrieveAndGenerateCommand(input);

  try {
    const response = await agentClient.send(command);
    console.log("Amazon Bedrock Response:", response.output?.text);
    console.log("Amazon Bedrock citations:", JSON.stringify(response.citations));
    // response.output?.text に回答テキスト、response.citationsに出典情報が含まれる想定
    return {
      answer: response.output?.text,
      citations: response.citations
    };
  } catch (error) {
    console.error("Amazon Bedrock API エラー:", error);
    return { answer: null, citations: null };
  }
}

// 汎用GPT問い合わせ関数（OpenAI API利用、モデル指定可能）
// systemMessageが空の場合はユーザーメッセージのみで問い合わせます。
async function queryGPTGeneric(model, systemMessage, userMessage) {
  const messages = [];
  if (systemMessage) {
    messages.push({ role: "system", content: systemMessage });
  }
  messages.push({ role: "user", content: userMessage });

  try {
    const response = await axios.post("https://api.openai.com/v1/chat/completions", {
      model: model,
      messages: messages,
    }, {
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${OPENAI_API_KEY}`
      }
    });
    return response.data.choices[0].message.content.trim();
  } catch (error) {
    console.error("OpenAI API エラー:", error.response?.data || error);
    return "回答の生成に失敗しました。";
  }
}

// 新規：会話形式のGPT問い合わせ関数（messages配列を直接送信）
async function queryGPTChat(payload) {
  try {
    const response = await axios.post("https://api.openai.com/v1/chat/completions", payload, {
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${OPENAI_API_KEY}`
      }
    });
    return response.data.choices[0].message.content.trim();
  } catch (error) {
    console.error("OpenAI API エラー:", error.response?.data || error);
    return "回答の生成に失敗しました。";
  }
}

// Slackにメッセージを投稿する関数
async function postSlackMessage(channel, text, thread_ts) {
  try {
    await axios.post("https://slack.com/api/chat.postMessage", {
      channel: channel,
      text: text,
      thread_ts: thread_ts,
    }, {
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${SLACK_BOT_TOKEN}`
      }
    });
  } catch (error) {
    console.error("Slack API エラー:", error.response?.data || error);
    throw error;
  }
}

// スレッド内メッセージを取得する関数
async function getThreadMessages(channel, thread_ts) {
  try {
    const response = await axios.get("https://slack.com/api/conversations.replies", {
      params: {
        channel: channel,
        ts: thread_ts
      },
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${SLACK_BOT_TOKEN}`
      }
    });
    if (response.data.ok) {
      return response.data.messages;
    } else {
      console.error("Slack API conversations.replies エラー:", response.data);
      return [];
    }
  } catch (error) {
    console.error("Slack API conversations.replies エラー:", error.response?.data || error);
    return [];
  }
}

exports.slackBot = functions.https.onRequest(app);