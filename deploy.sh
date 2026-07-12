#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Memento-X Cloud — ECS 一键部署脚本
# 目标服务器: 118.31.189.101
# 域名: memento.asia
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

echo "=========================================="
echo " Memento-X Cloud ECS 部署"
echo " 目标: 118.31.189.101"
echo " 域名: memento.asia"
echo "=========================================="

# ── 1. 检查 Docker 环境 ──
echo ""
echo "[1/5] 检查 Docker 环境..."
if ! command -v docker &>/dev/null; then
    echo "  Docker 未安装，正在安装..."
    curl -fsSL https://get.docker.com | bash
    systemctl enable docker && systemctl start docker
else
    echo "  Docker ✓ ($(docker --version))"
fi

if ! command -v docker-compose &>/dev/null && ! docker compose version &>/dev/null 2>&1; then
    echo "  docker-compose 未安装，正在安装..."
    apt-get update -qq && apt-get install -y -qq docker-compose-plugin
else
    echo "  docker-compose ✓"
fi

# ── 2. 拉取代码 ──
echo ""
echo "[2/5] 拉取最新代码..."
REPO_DIR="/opt/memento-x"
if [ -d "$REPO_DIR/.git" ]; then
    cd "$REPO_DIR"
    git pull origin main
else
    git clone https://github.com/eneatlnc-cell/Memento-X.git "$REPO_DIR"
    cd "$REPO_DIR"
fi

# ── 3. 配置环境变量 ──
echo ""
echo "[3/5] 配置环境变量..."
if [ ! -f "cloud/.env" ]; then
    cp cloud/.env.production cloud/.env
    echo "  cloud/.env 已从 .env.production 创建"
    echo "  ⚠️ 请编辑 cloud/.env 填入 OSS 相关配置"
else
    echo "  cloud/.env 已存在，跳过"
fi

# ── 4. 构建并启动 ──
echo ""
echo "[4/5] 构建并启动服务..."
docker compose build --no-cache cloud
docker compose up -d

# ── 5. 验证 ──
echo ""
echo "[5/5] 验证部署..."
sleep 5

# 健康检查
echo "  健康检查..."
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "  ✓ 本地健康检查通过"
    curl -s http://localhost:8000/health | python3 -m json.tool
else
    echo "  ✗ 本地健康检查失败，查看日志:"
    docker compose logs --tail=30 cloud
fi

# 外网检查
echo ""
echo "  外网检查..."
if curl -sf --connect-timeout 5 http://memento.asia/health > /dev/null 2>&1; then
    echo "  ✓ memento.asia 可访问"
else
    echo "  - memento.asia 暂不可达 (DNS 可能尚未生效或防火墙未开放 80/443)"
fi

echo ""
echo "=========================================="
echo " 部署完成!"
echo ""
echo " 端点:"
echo "  本地: http://localhost:8000"
echo "  外网: http://memento.asia"
echo "  健康: http://memento.asia/health"
echo "  API:  http://memento.asia/api/v1/"
echo "  Docs: http://memento.asia/docs"
echo ""
echo " 常用命令:"
echo "  查看日志: docker compose logs -f cloud"
echo "  重启服务: docker compose restart cloud"
echo "  停止服务: docker compose down"
echo "  数据库:   docker compose exec postgres psql -U memento"
echo "=========================================="