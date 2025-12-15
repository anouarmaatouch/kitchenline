# 🍕 Restaurant AI Voice Agent

An AI-powered voice ordering system that answers phone calls, takes restaurant orders using natural conversation, and manages orders through a real-time dashboard.

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-3.0-green.svg)
![OpenAI](https://img.shields.io/badge/OpenAI-Realtime_API-412991.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## 🎯 Overview

This project creates a fully automated phone ordering experience for restaurants. When customers call, they speak with an AI agent that understands natural language, takes their order, and submits it directly to the restaurant's order management system.

## ✨ Features

### 🤖 AI Voice Agent
- **Real-time voice conversation** using OpenAI's GPT-4o Realtime API
- **Natural language understanding** for complex orders with modifications
- **Customizable personality and menu** per restaurant
- **Voice selection** (alloy, echo, fable, nova, onyx, sage, shimmer)
- **Automatic order extraction** with customer name and delivery address

### 📱 Order Management Dashboard
- **Real-time order updates** via Server-Sent Events (SSE)
- **Order status workflow**: Received → In Progress → Ready → Delivered
- **Edit/delete orders** at any stage
- **Mobile-responsive design**

### 🔔 Push Notifications
- **Web Push notifications** when new orders arrive
- **Works even when phone is locked** (PWA support)
- **VAPID-based** secure notifications

### 👨‍💼 Admin Panel
- **User management** (create, edit, delete staff accounts)
- **Per-user settings**: custom system prompt, menu, voice selection
- **Agent toggle** to enable/disable AI answering per phone line
- **Menu upload** with AI-powered image-to-text extraction

### 📞 Telephony Integration
- **Vonage Voice API** for incoming call handling
- **WebSocket audio streaming** for real-time voice processing
- **Configurable phone number routing**

## 🛠️ Technology Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.9+, Flask, Gunicorn, Gevent |
| **Database** | PostgreSQL, SQLAlchemy ORM |
| **AI/Voice** | OpenAI GPT-4o Realtime API, Whisper |
| **Telephony** | Vonage Voice API, WebSocket |
| **Push Notifications** | Web Push (VAPID), pywebpush |
| **Real-time** | Server-Sent Events (SSE), Flask-Sock |
| **Auth** | Flask-Login, Werkzeug password hashing |
| **Deployment** | Docker, Docker Compose, Fly.io |

## 📁 Project Structure

```
restau/
├── app.py                 # Flask application factory
├── config.py              # Environment configuration
├── models.py              # SQLAlchemy models (User, Order, PushSubscription)
├── extensions.py          # Flask extensions (db, sock)
├── routes/
│   ├── auth.py            # Authentication routes
│   ├── orders.py          # Order CRUD + SSE
│   ├── admin.py           # Admin panel routes
│   ├── voice.py           # Vonage webhooks + OpenAI bridge
│   └── notifications.py   # Web Push notifications
├── templates/
│   ├── dashboard.html     # Main order management UI
│   ├── admin.html         # Admin panel UI
│   └── login.html         # Authentication UI
├── static/
│   └── sw.js              # Service Worker for push notifications
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 🚀 Getting Started

### Prerequisites
- Python 3.9+
- Docker & Docker Compose
- Vonage Account (for phone number)
- OpenAI API Key (with Realtime API access)

### Local Development

1. **Clone and setup environment**
```bash
git clone https://github.com/yourusername/restaurant-ai-voice.git
cd restaurant-ai-voice
cp .env.example .env
# Edit .env with your API keys
```

2. **Start with Docker Compose**
```bash
docker-compose up -d
```

3. **Initialize database**
```bash
docker-compose exec web python create_admin.py
```

4. **Access the dashboard**
- Open http://localhost:5000
- Login with `admin` / `password123`

### Production Deployment (Fly.io)

```bash
fly launch
fly secrets set OPENAI_API_KEY=sk-... VAPID_PRIVATE_KEY=... VAPID_PUBLIC_KEY=...
fly deploy
```

## ⚙️ Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | Flask session secret |
| `OPENAI_API_KEY` | OpenAI API key |
| `VONAGE_API_KEY` | Vonage API key |
| `VONAGE_API_SECRET` | Vonage API secret |
| `VONAGE_APPLICATION_ID` | Vonage application ID |
| `VAPID_PUBLIC_KEY` | Web Push public key |
| `VAPID_PRIVATE_KEY` | Web Push private key |
| `PUBLIC_URL` | Your public domain (e.g., `app.fly.dev`) |

## 📞 Vonage Configuration

Configure your Vonage application webhooks:
- **Answer URL**: `https://your-domain.com/webhooks/answer`
- **Event URL**: `https://your-domain.com/webhooks/event`

## 📄 License

MIT License - feel free to use this project for your own restaurant or as a portfolio piece!

## 🙏 Acknowledgments

- [OpenAI Realtime API](https://platform.openai.com/docs/guides/realtime) for voice AI
- [Vonage](https://vonage.com) for telephony
- [Fly.io](https://fly.io) for easy deployment
