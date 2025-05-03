# LINE-DeltaChat Bridge

A bridge application that connects LINE messaging with Delta Chat, enabling seamless communication between the two platforms.

## Features

- Forward messages between LINE and Delta Chat
- Support for text messages, images, and stickers
- Persistent conversation mapping
- Profile picture and name synchronization
- Docker deployment

## Installation with Docker

1. **Clone the repository:**

```
git clone https://github.com/yourusername/line-deltachat-bridge.git
cd line-deltachat-bridge
```

2. **Configure environment variables**: Edit docker-compose.yml and set your:

- LINE_CHANNEL_ACCESS_TOKEN
- LINE_CHANNEL_SECRET
- MY_DC_EMAIL (your Delta Chat email)
- DC_EMAIL (same as MY_DC_EMAIL)
- DC_PASSWORD
- NGROK_DOMAIN
- NGROK_AUTHTOKEN

3. **Build and run**:

```
docker compose up --build -d
```

4. **View logs**:

```
docker compose logs -f
```

## Configuration

**LINE Bot Setup**

1. Create a LINE Messaging API channel at developers.line.biz
2. Get your Channel Access Token and Channel Secret
3. Set the webhook URL to https://your-ngrok-domain.ngrok-free.app/callback
4. Enable webhooks and disable auto-reply messages

**Delta Chat Account Setup**

1. Create a Delta Chat email account that will serve as the bridge
2. Use this email in the configuration

**Ngrok Setup**

1. Create a ngrok account at ngrok.com
2. Get an authtoken and optionally a reserved domain
3. Configure these in your setup

## Usage

1. After starting the bridge, send a message from LINE to your bot
2. The message will appear in Delta Chat
3. Reply from Delta Chat to continue the conversation

## Troubleshooting

- Check logs using docker compose logs -f
- Ensure ngrok is properly connected
- Verify LINE webhook settings
- Confirm Delta Chat account credentials are correct