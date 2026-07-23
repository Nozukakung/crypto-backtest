#!/bin/bash
# run_web.sh — ดับเบิลคลิกเพื่อรัน Web Dashboard (Backend + Frontend + เปิด Browser)

set -e

# ตรวจจับว่ารันใน terminal หรือดับเบิลคลิกจาก GUI
if [ -t 0 ]; then
    # ถ้าเปิดจาก CLI/Terminal อยู่แล้ว: รันสคริปต์ปกติ
    echo "Running inside an existing terminal..."
else
    # ถ้าดับเบิลคลิกเปิดจาก GUI: ให้เปิดหน้าต่าง Terminal ใหม่ขึ้นมาและรันตัวเอง
    if command -v gnome-terminal &>/dev/null; then
        exec gnome-terminal -- bash -c "$0; echo 'Press Enter to close...'; read"
        exit 0
    elif command -v konsole &>/dev/null; then
        exec konsole -e bash -c "$0; echo 'Press Enter to close...'; read"
        exit 0
    elif command -v xterm &>/dev/null; then
        exec xterm -e bash -c "$0; echo 'Press Enter to close...'; read"
        exit 0
    fi
fi

# โหลด nvm เพื่อใช้ Node v22
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"

# บังคับใช้ Node v22
nvm use 22 >/dev/null 2>&1 || true

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/web/backend"
FRONTEND_DIR="$PROJECT_DIR/web/frontend"

# สีสำหรับ output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}======================================"
echo -e "🚀 Crypto Backtest Dashboard Launcher"
echo -e "======================================${NC}"
echo

# ตรวจสอบ dependencies
if [ ! -d "$BACKEND_DIR/node_modules" ]; then
    echo -e "${YELLOW}📦 Installing backend dependencies...${NC}"
    cd "$BACKEND_DIR" && npm install
fi

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo -e "${YELLOW}📦 Installing frontend dependencies...${NC}"
    cd "$FRONTEND_DIR" && npm install
fi

# ฟังก์ชัน cleanup ตอนปิด
cleanup() {
    echo -e "\n${YELLOW}🛑 Shutting down servers...${NC}"
    [ -n "$BACKEND_PID" ] && kill $BACKEND_PID 2>/dev/null
    [ -n "$FRONTEND_PID" ] && kill $FRONTEND_PID 2>/dev/null
    # Kill any child processes
    pkill -P $$ 2>/dev/null
    echo -e "${GREEN}✅ Done. Goodbye!${NC}"
    exit 0
}

trap cleanup INT TERM EXIT

# ฆ่า process ค้างที่พอร์ต 5001 (ถ้ามี)
lsof -ti :5001 | xargs -r kill -9 2>/dev/null || true
sleep 1

# 1. เริ่ม Backend
echo -e "${GREEN}▶ Starting Backend API (port 5001)...${NC}"
cd "$BACKEND_DIR"
node index.js > /tmp/backend.log 2>&1 &
BACKEND_PID=$!

# รอ Backend พร้อม
for i in {1..10}; do
    if curl -s http://localhost:5001/api/runs > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Backend ready!${NC}"
        break
    fi
    sleep 1
done

# 2. เริ่ม Frontend
echo -e "${GREEN}▶ Starting Frontend (Vite dev server)...${NC}"
cd "$FRONTEND_DIR"
npm run dev > /tmp/frontend.log 2>&1 &
FRONTEND_PID=$!

# รอ Frontend พร้อม (Vite ใช้เวลาประมาณ 3-5 วินาที)
echo -e "${YELLOW}⏳ Waiting for frontend to compile...${NC}"
sleep 5

# 3. เปิด Browser อัตโนมัติ
echo -e "${GREEN}🌐 Opening browser...${NC}"
xdg-open http://localhost:5173 2>/dev/null || open http://localhost:5173 2>/dev/null

# 4. แสดงสถานะและรอ
echo -e "\n${BLUE}======================================"
echo -e "✨ Dashboard is running!"
echo -e "======================================${NC}"
echo -e "📊 Backend API:  http://localhost:5001"
echo -e "🌐 Frontend:     http://localhost:5173"
echo -e "📁 Data source:  $PROJECT_DIR/results/backtest.db (SQLite)"
echo -e "\n${YELLOW}Press ENTER or close this window to stop...${NC}"

# รอผู้ใช้กด Enter (หรือปิด terminal)
read -r

# cleanup จะถูกเรียกอัตโนมัติผ่าน trap