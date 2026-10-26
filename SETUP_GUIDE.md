# Smart-LLM-Optimizer — hướng dẫn cài đặt

Tài liệu này dành cho người clone repository trên máy mới và muốn chạy hệ thống bằng Docker Compose.

## 1. Yêu cầu

- Git
- Docker Desktop đang chạy
- Docker Compose v2
- Tối thiểu 8 GB RAM cho Docker Desktop nếu bật adaptive prompt/LLMLingua
- Một API key của provider được cấu hình trong model catalog, tối thiểu `GROQ_API_KEY` cho cấu hình Groq hiện tại

Kiểm tra Docker:

```powershell
docker --version
docker compose version
```

## 2. Clone source code

```powershell
git clone <REPOSITORY_URL> Smart-LLM-Optimizer
cd Smart-LLM-Optimizer
```

Thay `<REPOSITORY_URL>` bằng URL repository thật.

## 3. Tạo file cấu hình môi trường

Không commit `.env` vì file này chứa secret.

```powershell
Copy-Item .env.example .env
notepad .env
```

Thiết lập tối thiểu:

```env
PROVIDER_MODE=live
GROQ_API_KEY=your_groq_api_key
ADAPTIVE_PROMPT_ENABLED=true
HYBRID_CONTEXT_ENABLED=true
MEMORY_RETRIEVAL_ENABLED=true
AUTO_ROUTING_STRATEGY=ml_multi_model
ML_ROUTER_ARTIFACT_PATH=config/router_multitask_vietnamese_model.json
ML_ROUTER_LIVE_APPROVED=false
```

Nếu dùng OpenRouter hoặc OpenAI, điền thêm các key tương ứng:

```env
OPENROUTER_API_KEY=your_openrouter_api_key
OPENAI_API_KEY=your_openai_api_key
```

Không dùng key giả khi chạy `PROVIDER_MODE=live`.

## 4. Kiểm tra cấu hình Compose

```powershell
docker compose config
```

Nếu lệnh này báo lỗi, kiểm tra lại `.env`, đặc biệt là các biến có giá trị rỗng hoặc dấu ngoặc kép không hợp lệ.

## 5. Build và chạy hệ thống

```powershell
docker compose up -d --build --force-recreate
```

Kiểm tra container:

```powershell
docker compose ps
docker compose logs backend --tail=100
```

Backend chạy tại `http://localhost:8000` và frontend chạy tại `http://localhost:3000`.

Kiểm tra backend:

```powershell
Invoke-WebRequest http://localhost:8000/v1/platform-info
```

Mở giao diện:

```text
http://localhost:3000
```

## 6. Xác nhận các module chính

Kiểm tra cấu hình bên trong container:

```powershell
docker compose exec backend python -c "from app.config import Settings; s=Settings(); print({'adaptive': s.adaptive_prompt_enabled, 'context': s.hybrid_context_enabled, 'memory': s.memory_retrieval_enabled})"
```

Kết quả mong muốn:

```text
{'adaptive': True, 'context': True, 'memory': True}
```

### Router ML

Gửi một câu hỏi rồi mở **Trace**. Dòng router cần có dạng:

```text
ROUTE_ML_MULTI_CANDIDATE
```

Nếu thấy `ML_MODEL_MISMATCH_FALLBACK` hoặc `ML_CATALOG_CHANGED_FALLBACK`, kiểm tra:

- `ML_ROUTER_ARTIFACT_PATH`
- `ML_ROUTER_LIVE_APPROVED`
- model catalog trong `config/models.json`
- artifact có được train từ đúng catalog hiện tại hay không

### Adaptive prompt

Gửi prompt dài hơn khoảng 500 token. Trong **Trace** kiểm tra:

```text
rewrite: applied
reason: llmlingua2
before_tokens: <lớn hơn>
after_tokens: <nhỏ hơn>
```

Nếu prompt ngắn, `under_threshold` là hành vi bình thường. Nếu model LLMLingua chưa được tải, lần chạy đầu có thể chậm vì phải tải model từ Hugging Face.

### Memory

Trong session đầu tiên gửi:

```text
My name is Minh. I prefer concise answers.
```

Mở session mới bằng cùng tài khoản rồi hỏi:

```text
What do you know about my name and preferences?
```

Trace của session mới cần có:

```text
memory: applied
reason: memory_retrieval
```

Memory chỉ được truy hồi giữa các session thuộc cùng user; `no_relevant_memory` nghĩa là chưa tìm thấy fact phù hợp.

## 7. Chạy test

```powershell
docker compose exec backend pytest -q
```

Nếu chỉ muốn test adaptive prompt và memory:

```powershell
docker compose exec backend pytest -q app/optimizers app/memory
```

## 8. Dừng và reset dữ liệu local

Dừng container:

```powershell
docker compose down
```

Không xóa thư mục `data` nếu muốn giữ database, memory và trace. Muốn reset dữ liệu local, hãy sao lưu trước rồi mới xóa các file database tương ứng.

## 9. Lỗi thường gặp

### Container không start

```powershell
docker compose logs backend --tail=200
docker compose logs frontend --tail=200
```

### API trả lỗi provider

Kiểm tra API key và model catalog:

```powershell
docker compose exec backend python -c "import os; print('GROQ_API_KEY configured=', bool(os.getenv('GROQ_API_KEY')))"
```

Không in giá trị thật của API key ra terminal hoặc gửi vào issue.

### Adaptive prompt chạy rất lâu

LLMLingua chạy CPU và có thể tải model lần đầu. Kiểm tra RAM Docker Desktop và log backend. Có thể tạm thời đặt:

```env
ADAPTIVE_PROMPT_ENABLED=false
```

### Router fallback

Đừng sửa tay artifact hoặc nhãn dataset. Kiểm tra catalog, hash artifact và log Trace trước khi train lại.

## 10. Checklist trước khi bàn giao

- [ ] Người nhận đã clone được repository.
- [ ] `.env` được tạo riêng và không commit vào Git.
- [ ] `docker compose config` chạy không lỗi.
- [ ] Backend health check trả HTTP 200.
- [ ] Frontend mở được tại port 3000.
- [ ] Router có Trace hợp lệ.
- [ ] Adaptive prompt có before/after tokens.
- [ ] Memory truy hồi được ở session mới.
- [ ] Test backend pass.
- [ ] API key và dữ liệu cá nhân không nằm trong source hoặc screenshot.

Artifact ML hiện tại là artifact đã train cho catalog/provider đã được thu thập. Nếu thay đổi model catalog hoặc provider, cần đánh giá và train/alignment lại trước khi dùng artifact đó trong live routing.
