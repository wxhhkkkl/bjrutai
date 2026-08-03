const test = require('node:test');
const assert = require('node:assert/strict');
const {
  MAX_SCREENSHOTS,
  HELP_FAQS,
  FEEDBACK_TYPES,
  normalizeFeedbackType,
  validateFeedback,
  createFeedbackRecord
} = require('../../models/help-feedback');

test('help feedback exposes approved faq and type choices', () => {
  assert.equal(HELP_FAQS.length, 3);
  assert.equal(FEEDBACK_TYPES.length, 3);
  assert.equal(normalizeFeedbackType('suggestion'), 'suggestion');
  assert.equal(normalizeFeedbackType('unsupported'), 'issue');
});

test('feedback requires a useful description and limits screenshots', () => {
  assert.equal(
    validateFeedback({
      type: 'issue',
      content: '太短',
      images: []
    }).field,
    'content'
  );
  assert.equal(
    validateFeedback({
      type: 'issue',
      content: '客户绑定页面点击提交后没有任何反馈',
      images: new Array(MAX_SCREENSHOTS + 1).fill('wxfile://image.png')
    }).field,
    'images'
  );
  assert.equal(
    validateFeedback({
      type: 'suggestion',
      content: '建议增加客户筛选条件并保存常用筛选方案',
      images: ['wxfile://image.png']
    }).valid,
    true
  );
});

test('feedback record normalizes data for persistence', () => {
  const record = createFeedbackRecord({
    type: 'suggestion',
    content: '  建议增加客户筛选条件并保存常用筛选方案  ',
    images: ['wxfile://one.png']
  }, 100);

  assert.equal(record.id, 'feedback-100');
  assert.equal(record.type, 'suggestion');
  assert.equal(record.content, '建议增加客户筛选条件并保存常用筛选方案');
  assert.deepEqual(record.images, ['wxfile://one.png']);
  assert.equal(record.status, 'submitted');
});
