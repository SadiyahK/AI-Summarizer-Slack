import json
import boto3
import urllib.parse
import urllib3
import os
from botocore.response import StreamingBody

bedrock = boto3.client(service_name='bedrock-runtime')
slackUrl = 'https://slack.com/api/chat.postMessage'
slackToken = os.environ.get('token')

http = urllib3.PoolManager()

def call_bedrock(messages):
    body = json.dumps({
        "prompt": f"Summarise these messages to 3 bullet points. No yapping: {messages}",
        "temperature": 0.2,
        "top_p": 0.8,
    })

    modelId = 'meta.llama3-70b-instruct-v1:0'
    accept = 'application/json'
    contentType = 'application/json'

    response = bedrock.invoke_model(body=body, modelId=modelId, accept=accept, contentType=contentType)

    if isinstance(response.get('body'), StreamingBody):
        response_content = response['body'].read().decode('utf-8')
    else:
        response_content = response.get('body')

    response_body = json.loads(response_content)
    print(response_body)

    return response_body.get('generation')

def lambda_handler(event, context):
    slackBody = json.loads(event['body'])
    print("slack body")
    print(slackBody)

    # Extract details from the Slack event
    slackText = slackBody.get('event', {}).get('text')
    slackUser = slackBody.get('event', {}).get('user')
    channel = slackBody.get('event', {}).get('channel')
    thread_ts = slackBody.get('event', {}).get('thread_ts')

    # Check if the message is from the bot itself
    if slackUser == "A088GEDV5HP":
        return {'statusCode': 400, 'body': json.dumps({'msg': "Bot message ignored"})}

    if thread_ts:
        # If there's a thread timestamp, get the thread history
        history = get_thread_history(channel, thread_ts)
    else:
        # Otherwise, get the channel history
        history = get_channel_history(channel)

    print(history)
    messages = "\n ".join(extract_text_from_messages(history))
    print(messages)

    # Call the Bedrock model with the thread or channel message history
    msg = call_bedrock(messages)

    # Reply to the thread if `thread_ts` is present
    if thread_ts:
        post_message_to_thread(channel, msg, slackUser, thread_ts)
    else:
        post_message_to_channel(channel, msg, slackUser)

    # Return a successful response
    return {
        'statusCode': 200,
        'body': json.dumps({'msg': "message received"})
    }

def post_message_to_thread(channel, text, slackUser, thread_ts):
    data = {
        'channel': channel,
        'text': f"<@{slackUser}> {text}",
        'thread_ts': thread_ts
    }
    headers = {
        'Authorization': f'Bearer {slackToken}',
        'Content-Type': 'application/json',
    }
    response = http.request('POST', slackUrl, headers=headers, body=json.dumps(data))
    if response.status != 200:
        print(f"Failed to send message: {response.data.decode('utf-8')}")

def post_message_to_channel(channel, text, slackUser):
    data = {
        'channel': channel,
        'text': f"<@{slackUser}> {text}"
    }
    headers = {
        'Authorization': f'Bearer {slackToken}',
        'Content-Type': 'application/json',
    }
    response = http.request('POST', slackUrl, headers=headers, body=json.dumps(data))
    if response.status != 200:
        print(f"Failed to send message: {response.data.decode('utf-8')}")

def get_channel_history(channel_id, limit=100):
    url = "https://slack.com/api/conversations.history"
    headers = {
        "Authorization": f"Bearer {slackToken}"
    }
    params = {
        "channel": channel_id,
        "limit": limit
    }

    query_string = urllib.parse.urlencode(params)
    request_url = f"{url}?{query_string}"

    req = http.request('GET', request_url, headers=headers)

    try:
        data = json.loads(req.data.decode())
        if data.get("ok"):
            return data.get("messages", [])
        else:
            print(f"Error fetching history: {data.get('error')}")
            return []
    except Exception as e:
        print(f"Error: {e}")
        return []

def get_thread_history(channel_id, thread_ts, limit=100):
    url = "https://slack.com/api/conversations.replies"
    headers = {
        "Authorization": f"Bearer {slackToken}"
    }
    params = {
        "channel": channel_id,
        "ts": thread_ts,
        "limit": limit
    }

    query_string = urllib.parse.urlencode(params)
    request_url = f"{url}?{query_string}"

    req = http.request('GET', request_url, headers=headers)

    try:
        data = json.loads(req.data.decode())
        if data.get("ok"):
            return data.get("messages", [])
        else:
            print(f"Error fetching thread history: {data.get('error')}")
            return []
    except Exception as e:
        print(f"Error: {e}")
        return []

def extract_text_from_messages(messages):
    text_messages = []
    for message in messages:
        if 'text' in message:
            text_messages.append(message['text'])
    return text_messages
