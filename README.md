# 🎮 Game Update Server

A Flask-based game update server with launcher management, built for containerized deployment.

## ✨ Features

- **🚀 Launcher Distribution**: Public download page for game launcher
- **🎮 Game Version Management**: Upload and manage game versions
- **📊 Admin Dashboard**: Web-based administration interface
- **🔐 User Management**: Multi-user admin system with authentication
- **📡 REST API**: JSON API for launcher integration
- **🐳 Docker Ready**: Fully containerized with daily automated builds

## 🚀 Quick Start

### Using Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/NerdsCorp/python-docker.git
cd python-docker

# Start the server
docker-compose up -d

# Access the application
open http://localhost:8000
```

### Using Pre-built Container

```bash
# Pull the latest image
docker pull ghcr.io/nerdscorp/game-update-server:latest

# Run with persistent data
docker run -d \
  --name game-update-server \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/downloads:/app/downloads \
  ghcr.io/nerdscorp/game-update-server:latest
```

## 🌐 Access Points

- **Public Launcher Page**: http://localhost:8000/
- **Admin Dashboard**: http://localhost:8000/admin
- **Default Login**: `admin` / `admin123`
- **API Endpoint**: http://localhost:8000/api/version
- **Launcher API**: http://localhost:8000/api/launcher/version
- **Health Check**: http://localhost:8000/api/health

## 🔧 Configuration

### Environment Variables

Create a `.env` file for production:

```bash
FLASK_SECRET_KEY=your-super-secure-random-key
BASE_URL=https://updates.yourdomain.com
FLASK_ENV=production
FLASK_DEBUG=False
MAX_CONTENT_LENGTH=5368709120  # 5GB upload limit
```

### Data Persistence

The container uses two volumes:
- `/app/data` - Database and configuration files
- `/app/downloads` - Uploaded game files

## 🔒 Security Features

- **Non-root container execution**
- **Secure file upload handling**
- **Password hashing for user authentication**
- **Session-based admin access**
- **File size limits and validation**

## 📡 API Endpoints

### Game Version API
- `GET /api/version` - Get current active game version
- `GET /api/version/history` - Get all game versions
- `POST /api/version/{version}/activate` - Activate a version
- `DELETE /api/version/{version}` - Delete a version

### Launcher API
- `GET /api/launcher/version` - Get current launcher version
- `GET /api/launcher/history` - Get all launcher versions
- `POST /api/launcher/version/{version}/activate` - Activate launcher version
- `DELETE /api/launcher/version/{version}` - Delete launcher version

### Upload API
- `POST /api/upload` - Upload new game or launcher version

## 🔄 Automated Builds

This repository includes GitHub Actions that automatically:
- **Build and test** the container on every push
- **Publish to GitHub Container Registry** daily at midnight UTC
- **Support multiple architectures** (AMD64 and ARM64)
- **Tag with date and version** for easy rollbacks

## 🛠️ Development

### Local Development Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
python server.py

# Access at http://localhost:5000
```

### Building the Container

```bash
# Build locally
docker build -t game-update-server .

# Run locally built image
docker run -p 8000:8000 game-update-server
```

## 📦 Container Details

- **Base Image**: Python 3.11 slim
- **Web Server**: Gunicorn with 4 workers
- **Port**: 8000 (internal and external)
- **Health Check**: Built-in endpoint monitoring
- **Security**: Runs as non-root user
- **Size**: Optimized for minimal footprint

## 🔍 Monitoring

The container includes health checks accessible at:
- `GET /health` - Simple health status
- `GET /api/health` - Detailed health information

## 📊 Admin Features

- **Upload Management**: Drag-and-drop file uploads up to 5GB
- **Version Control**: Activate/deactivate versions instantly
- **User Management**: Create and manage admin users
- **Release Notes**: Detailed changelog for each version
- **File Analytics**: View download counts and file sizes

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with Docker
5. Submit a pull request

## 📄 License

This project is part of NerdsCorp's internal tooling.

---

**Built with ❤️ by NerdsCorp**
