# Bàn giao SmartLLM cho máy lab Linux

Code: nhánh `Fix/Huy/linux-lab-handoff-20261027`, đích merge `develop`. Kiểm tra trạng thái remote thực tế trước khi deploy; tài liệu này không tự chứng minh đã push/merge.

## Gói gửi riêng

`smartllm-linux-private-20261027.zip` chứa secret thật theo yêu cầu của Huy. Chỉ gửi riêng cho người quản trị máy lab, không upload GitHub/issue/log. Gồm `.env` dành cho Linux, `.env.source-private` là bản gốc để đối chiếu, `config/models.json` không chứa key, SQLite backup đã kiểm tra toàn vẹn, uploads, encoder ONNX/tokenizer, cache compressor được chuyển thành file thường để Linux đọc được và manifest hash. Không có node_modules, .venv, .next, WAL/SHM hoặc host database hỏng.

Database là backup nhất quán lúc **22:53:34 ngày 27/10/2026 giờ Việt Nam**, không phải bản sao nóng của WAL. Giữ nguyên tài khoản/password hash, chat, ledger, reservation chưa đối soát. Không tự giải phóng khoản chưa rõ, không tự resume job thu dữ liệu. Nếu có chat mới sau mốc snapshot, cần tạo backup mới trước khi chuyển hẳn máy.

## Chạy bằng Docker trên Linux

Clone repo rồi chuyển `develop` sau khi merge được xác nhận. Giải nén ZIP ngay thư mục root repo. Kiểm tra `manifest.json`; không ghi đè một database đang chạy. `.env` vẫn bị Git ignore.

```bash
chmod 600 .env .env.source-private
docker compose build
docker compose create backend
# Volume phải mới/trống; KHÔNG ghi đè dữ liệu máy lab đã có.
docker compose run --rm --no-deps --entrypoint python backend -c 'from pathlib import Path; import sqlite3; src=Path("/app/data/smartllm.db"); dst=Path("/app/runtime-db/smartllm.db"); assert not dst.exists(), "Existing database: stop and back it up"; a=sqlite3.connect(src.as_uri()+"?mode=ro",uri=True); b=sqlite3.connect(dst); a.backup(b); assert b.execute("PRAGMA integrity_check").fetchone()[0]=="ok"; b.close(); a.close()'
docker compose up -d
curl -f http://localhost:8000/v1/health/ready
curl -f http://localhost:3000/api/v1/health/ready
```

Docker entrypoint chạy migration đến h108. Native Linux volume giữ SQLite; thư mục `data/` giữ uploads/assets. Giữ một backend worker. Truy cập `http://localhost:3000`; từ máy khác dùng địa chỉ máy lab và thêm đúng origin đó vào `ALLOWED_ORIGINS` trong `.env`. HTTP local dùng `COOKIE_SECURE=false`; HTTPS dùng true. Không đổi quota/key limit chỉ để thử.

## Chạy không Docker

Node 24.x, npm 11.x, Python 3.11; chạy ở root repo. Không dùng Windows `.venv` trên Linux.

```bash
npm ci
python3.11 -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r backend/requirements.lock
pip install --no-deps --require-hashes -r backend/requirements-router-serving.lock
pip install --no-deps --require-hashes -r backend/requirements-validation.lock
pip install --no-deps -e './backend[dev]'
pip check
export SMARTLLM_ROOT="$PWD"
export HF_HUB_CACHE="$PWD/data/huggingface/hub"
python -m alembic -c backend/alembic.ini upgrade head
npm run contracts:check
npm run typecheck
npm run lint
npm run test:backend
npm run test:frontend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# Terminal thứ hai, ở root:
BACKEND_URL=http://127.0.0.1:8000 npm run build
npm run start --workspace frontend
```

Các commands test phải dùng provider mock, không gọi API trả phí. `backend/tests/conftest.py` chặn network ngoài. Không chạy script audit live/collector chỉ để setup. Test thật trên browser dùng ngân sách/key của chủ hệ thống.

## Routing hiện tại

Gói env giữ cấu hình thử Huy yêu cầu: **20B=0,690085, Luna=0,71**, 120B là reference. Artifact mới là `config/router_attention_operator_thresholds_0690085_071.json`; receipt `config/router_operator_thresholds_acceptance.json`; evidence ghi passed=false. Các file được commit Git, không cần model cũ `router_multitask_vietnamese_model.json` để chạy cấu hình này. Giữ bản cũ để rollback. Đây là development trial được Huy chọn, chưa được chứng nhận chất lượng độc lập; không đổi thành qualified_dev.

## Hosting Render / Vercel

Render build theo `render-backend.Dockerfile`. Catalog ignored không tự có từ Git: tạo Secret File `models.json` và đặt `MODEL_CATALOG_PATH=/etc/secrets/models.json`, hoặc provision qua runtime volume. Không nhét API key vào catalog. Nhập riêng `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY` nếu dùng. `COOKIE_SECURE=true`, `ALLOWED_ORIGINS` là JSON array domain HTTPS thật; Vercel `BACKEND_URL=https://<backend-domain>` được cấu hình trước build rồi redeploy.

Render blueprint giữ cổng research tắt, không tự bật cấu hình ngưỡng thử của lab lên hosting công khai. Muốn chạy đủ Attention/nén trên hosting cần provision cả `data/router-assets/` và cache HF như ZIP; chỉ có artifact JSON là chưa đủ. Cần storage bền vững cho SQLite/uploads và đủ RAM cho encoder/compressor; blueprint hiện không cam kết phục vụ đầy đủ bằng tài nguyên miễn phí. Health dùng `/v1/health/ready`, metadata `/v1/platform-info` không thay cho kiểm tra storage.

Danh sách biến (secret values chỉ trong gói riêng): `PROVIDER_MODE`, `MODEL_CATALOG_PATH`, `DATABASE_PATH`, `UPLOAD_DIRECTORY`, `SMARTLLM_ROOT`, `HF_HUB_CACHE`, `APP_ENV`, `AUTO_ROUTING_STRATEGY`, `ML_ROUTER_ARTIFACT_PATH`, `ML_ROUTER_LIVE_APPROVED`, `ML_ROUTER_ALLOW_RESEARCH_CANDIDATE`, `ML_ROUTER_RESEARCH_ACCEPTANCE_PATH`, `ADAPTIVE_PROMPT_ENABLED`, `HYBRID_CONTEXT_ENABLED`, `MEMORY_RETRIEVAL_ENABLED`, `RESEARCH_LIVE_ENABLED`, `ALLOWED_ORIGINS`, `COOKIE_SECURE`, provider API keys, ngân sách và quota hiện có. Không gửi nguyên env qua kênh công khai.
