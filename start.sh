#!/bin/bash
# filepath: line-deltachat-bridge/start.sh
set -e

# Start deltachat-rpc-server via Python module
echo "Starting DeltaChat RPC server on port 23123..."
python -m deltachat.rpc.serve --listen 0.0.0.0:23123 &
RPC_PID=$!
sleep 3
echo "DeltaChat RPC server started with PID $RPC_PID"

# Update DELTACHAT_RPC_HOST in app.py to use localhost
sed -i "s/DELTACHAT_RPC_HOST = os.environ.get('DELTACHAT_RPC_HOST', '.*')/DELTACHAT_RPC_HOST = os.environ.get('DELTACHAT_RPC_HOST', '127.0.0.1')/" /app/app.py

# Start ngrok
echo "Starting ngrok..."
/usr/local/bin/ngrok config add-authtoken "$NGROK_AUTHTOKEN"
/usr/local/bin/ngrok http --domain="$NGROK_DOMAIN" 5000 &
sleep 3

# Get the ngrok URL
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | grep -o "https://[^\"]*" | head -1)
if [ -z "$NGROK_URL" ]; then
    NGROK_URL="https://$NGROK_DOMAIN"
fi
echo "NGROK URL: $NGROK_URL"
sed -i "s|NGROK_URL = os.environ.get('NGROK_URL', '.*')|NGROK_URL = os.environ.get('NGROK_URL', '$NGROK_URL')|g" /app/app.py

# Start the app
echo "Starting LINE-DeltaChat bridge..."
python app.py ${DC_EMAIL} ${DC_PASSWORD}