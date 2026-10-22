import asyncio
import json
import re
from time import perf_counter

from app.contracts.dtos import Message, ProviderItem, ProviderOptions, ProviderResult, ToolCall


class DeterministicMockProvider:
    async def generate(
        self, messages: tuple[Message, ...], opts: ProviderOptions
    ) -> ProviderResult:
        started = perf_counter()
        await asyncio.sleep(0)  # A real async boundary, no external inference.
        current = messages[-1].content
        if opts.tools and opts.continuation_items:
            outputs = [
                json.loads(i.payload_json).get("output", "")
                for i in opts.continuation_items
                if i.type == "function_call_output"
            ]
            return ProviderResult(
                text="[MOCK · tools]\n" + "\n".join(outputs),
                duration_ms=(perf_counter() - started) * 1000,
            )
        # Explicit deterministic fixtures, not a semantic intent classifier.
        expression = re.search(r"(?:tính|calculate)\s*:?\s*([0-9+*/().\s-]+)", current, re.I)
        doc_query = re.search(r"(?:tra cứu tài liệu|search documents)\s*:\s*(.+)", current, re.I)
        name = "calculate" if expression else "search_selected_documents" if doc_query else None
        if name and name in {t.name for t in opts.tools}:
            arguments = json.dumps(
                {"expression": expression.group(1).strip()}
                if expression
                else {"query": doc_query.group(1).strip() if doc_query else ""},
                ensure_ascii=False,
            )
            call = ToolCall(call_id="mock-tool-1", name=name, arguments=arguments)
            item = ProviderItem(
                type="function_call",
                payload_json=json.dumps(
                    {
                        "type": "function_call",
                        "call_id": call.call_id,
                        "name": name,
                        "arguments": arguments,
                    }
                ),
            )
            return ProviderResult(
                text="",
                status="tool_calls",
                tool_calls=(call,),
                output_items=(item,),
                duration_ms=(perf_counter() - started) * 1000,
            )
        lower = current.lower()
        if "học phí" in lower or "hạn đóng" in lower or "tiền học" in lower:
            answer = (
                f'Về câu hỏi của bạn: "{current}"\n\n'
                "• **Mức học phí tiêu chuẩn**: Được tính dựa trên tổng số tín chỉ đăng ký thực tế trong học kỳ (trung bình từ 15 – 20 tín chỉ/kỳ).\n"
                "• **Thời hạn nộp học phí**: Chưa xác định; cần đối chiếu thông báo của trường trong tài liệu được chọn.\n"
                "• **Phương thức nộp**: Sinh viên có thể thanh toán trực tuyến qua cổng thông tin tài chính sinh viên hoặc chuyển khoản qua ngân hàng liên kết.\n\n"
                "💡 *Gợi ý: Bạn có thể tải lên văn bản thông báo học phí ở mục tài liệu để tôi hỗ trợ đối chiếu chính xác nhất nhé!*"
            )
        elif "tóm tắt" in lower or "tổng hợp" in lower:
            answer = (
                f'Tóm tắt các điểm trọng tâm cho yêu cầu: "{current}"\n\n'
                "1. **Mục tiêu & Phạm vi**: Xác định các yêu cầu cốt lõi và lộ trình thực hiện theo quy chuẩn.\n"
                "2. **Các mốc thời gian then chốt**: Cần lưu ý các thời hạn nộp báo cáo và thời điểm kiểm tra tiến độ.\n"
                "3. **Lưu ý quan trọng**: Đảm bảo tuân thủ đầy đủ tài liệu nguồn để tránh thiếu sót thông tin đối chiếu."
            )
        elif "so sánh" in lower or "đối chiếu" in lower:
            answer = (
                f'Kết quả đối chiếu tổng quan theo yêu cầu: "{current}"\n\n'
                "• **Điểm tương đồng**: Cả hai nội dung đều hướng đến việc chuẩn hóa quy trình và tối ưu hóa thời gian xử lý.\n"
                "• **Điểm khác biệt**: Sự khác biệt chủ yếu nằm ở điều kiện tiên quyết và phương thức triển khai chi tiết của từng phần."
            )
        else:
            answer = (
                f'Chào bạn, tôi đã tiếp nhận yêu cầu: "{current}".\n\n'
                "Hệ thống đang hoạt động ở chế độ thử nghiệm nội bộ. "
                "Nếu bạn có tài liệu cần tra cứu hoặc câu hỏi chuyên sâu hơn, hãy tiếp tục đặt câu hỏi để cùng trao đổi nhé!"
            )

        return ProviderResult(
            text="Phản hồi minh họa trong chế độ giả lập; chưa phải phân tích từ mô hình thật.\n\n"
            + answer,
            duration_ms=(perf_counter() - started) * 1000,
        )
