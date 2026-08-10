from src.schemas.feedback import FeedbackCreateRequest
from src.services.feedback_service import _fingerprint


def test_feedback_fingerprint_keeps_attachment_order_and_normalizes_content():
    left = FeedbackCreateRequest(type="feature", content="  建议增加客户筛选能力  ", imageFiles=["feedbacks/1/a.png", "feedbacks/1/b.png"])
    same = FeedbackCreateRequest(type="suggestion", content="建议增加客户筛选能力", imageFiles=["feedbacks/1/a.png", "feedbacks/1/b.png"])
    reordered = FeedbackCreateRequest(type="suggestion", content="建议增加客户筛选能力", imageFiles=["feedbacks/1/b.png", "feedbacks/1/a.png"])
    assert _fingerprint(left) == _fingerprint(same)
    assert _fingerprint(left) != _fingerprint(reordered)
