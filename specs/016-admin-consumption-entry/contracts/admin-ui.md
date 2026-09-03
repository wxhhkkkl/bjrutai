# Admin UI Contract: 消费业绩页录入

## Entry point

- Route remains `/contributions` with title “消费业绩”.
- A primary “录入消费” button appears next to “刷新” only when the current account has `contributions.write`.
- Accounts with only `contributions.read` keep the existing read-only page behavior.

## Dialog

Title: “录入消费”

### Fields

1. **客户** — required remote search; searches name, phone or ID card.
2. **归属人员** — automatically shown after customer selection; read-only.
3. **所属组织** — automatically shown after customer selection; read-only.
4. **消费时间** — required date-time picker; defaults to now; future values disabled.
5. **实付金额（元）** — required; greater than 0; maximum two decimal places.
6. **备注** — optional; maximum 500 characters with counter.

Customer search choices display customer name, masked phone, masked ID card, person and organization. Raw sensitive values never appear in DOM text or client logs.

## Confirmation and submission

- Clicking “确认录入” first validates the form, then shows a confirmation summary with customer, attribution, time and formatted amount.
- Final confirmation calls the create endpoint with integer `amountCent` and a timezone-bearing `consumedAt`.
- While the request is pending, both final confirmation and dialog submit controls are disabled.
- On success: show “消费录入成功”, close and reset the dialog, then refresh dashboard and the active ranking tab.
- On recoverable failure: keep the dialog and all inputs; show the backend Chinese message.
- On customer-version conflict or ineligible-customer response: clear only the customer selection, retain time/amount/note, and ask the administrator to search and confirm again.
- Closing or cancelling the dialog does not submit data.

## Idempotency lifecycle

- Generate one key when a new form session starts.
- A failed retry with identical normalized content reuses the same key.
- Editing customer, time, amount or note after a failed attempt starts a new logical submission and generates a new key.
- A successful submission disposes of the key before the next form session.

## Latest detail display

- Add customer name and source columns to “最新消费明细（30 条）”.
- Source labels: `manual` → “人工录入”; `rutai_sync` → “儒泰同步”.
- Customer phone remains masked when shown in tooltip or secondary text.
- Existing amount, status, person, organization and time formats remain unchanged.

## Accessibility and feedback

- Every field has a visible Chinese label and validation message.
- Read-only attribution is visually distinct but remains readable.
- Loading, no-result, permission, validation, conflict and network messages are Chinese.
- Keyboard focus returns to “录入消费” after successful close.

