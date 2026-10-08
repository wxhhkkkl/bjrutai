const test = require('node:test');
const assert = require('node:assert/strict');
const {
  DOCUMENT_VERSION,
  USER_AGREEMENT,
  PRIVACY_POLICY,
  getLegalDocument
} = require('../../models/legal-document');

test('legal documents provide complete, project-specific sections', () => {
  assert.equal(getLegalDocument('agreement'), USER_AGREEMENT);
  assert.equal(getLegalDocument('privacy'), PRIVACY_POLICY);
  assert.equal(getLegalDocument('unsupported'), null);
  assert.equal(USER_AGREEMENT.version, DOCUMENT_VERSION);
  assert.ok(USER_AGREEMENT.sections.length >= 6);
  assert.ok(PRIVACY_POLICY.sections.length >= 6);
  assert.match(PRIVACY_POLICY.sections.flatMap((item) => item.paragraphs).join(''), /腾讯云对象存储/);
});

test('personal customers do not see distributor-only clauses in the user agreement', () => {
  const document = getLegalDocument('agreement', 'personal');
  const content = document.sections.flatMap((section) => section.paragraphs).join('\n');

  assert.doesNotMatch(content, /面向分销员提供账号登录/);
  assert.doesNotMatch(content, /账号中的分销员角色/);
  assert.doesNotMatch(content, /使用客户绑定、跟进或分析功能时/);
  assert.doesNotMatch(content, /客户绑定、解绑、跟进记录和消费贡献数据/);
  assert.deepEqual(document.sections.map((section) => section.title), [
    '一、服务说明',
    '二、账号与身份',
    '三、客户信息与业务协作',
    '四、信息与内容使用',
    '五、用户行为规范',
    '六、服务变更与中断',
    '七、知识产权',
    '八、协议更新与联系我们'
  ]);
  assert.match(content, /部分服务需要通过微信登录或授权手机号/);
  assert.match(content, /具体功能以小程序当前展示和后台配置为准/);
  assert.match(content, /不得提交与业务无关、虚假、违法或侵犯他人权益的内容/);
});

test('non-personal agreements and privacy policies remain unchanged', () => {
  assert.equal(getLegalDocument('agreement', 'collaborator'), USER_AGREEMENT);
  assert.equal(getLegalDocument('privacy', 'collaborator'), PRIVACY_POLICY);
  assert.equal(getLegalDocument('privacy'), PRIVACY_POLICY);
  assert.equal(getLegalDocument('agreement'), USER_AGREEMENT);
});

test('personal customers see privacy content without distributor-only details', () => {
  const document = getLegalDocument('privacy', 'personal');
  const content = document.sections.flatMap((item) => item.paragraphs).join('\n');

  assert.notEqual(document, PRIVACY_POLICY);
  assert.equal(document.intro, '儒泰医联重视您的个人信息和隐私保护。');
  assert.doesNotMatch(content, /业务信息：您主动录入或确认的客户姓名/);
  assert.doesNotMatch(content, /识别分销员身份|客户绑定与跟进|展示消费贡献/);
  assert.doesNotMatch(content, /消费记录同步和机构协作|所属机构及其授权的儒泰业务系统/);
  assert.match(content, /创建和维护账号、完成微信或手机号登录/);
  assert.match(content, /处理反馈以及保障服务安全/);
  assert.match(content, /共享范围限制在实现该功能所必需的范围内/);
  assert.match(content, /腾讯云对象存储/);
});

test('legal document page uses the authenticated session role', () => {
  const previousPage = global.Page;
  let pageDefinition;
  global.Page = (definition) => { pageDefinition = definition; };

  try {
    require('../../pages/legal-document/index');
    const { setSession, clearAuthenticatedSession } = require('../../services/session-service');
    setSession({ userId: 'customer-test', role: 'personal' });

    let document;
    pageDefinition.onLoad.call({ setData: (data) => { document = data.document; } }, { type: 'agreement' });
    const content = document.sections.flatMap((section) => section.paragraphs).join('\n');
    assert.doesNotMatch(content, /面向分销员提供账号登录/);
    pageDefinition.onLoad.call({ setData: (data) => { document = data.document; } }, { type: 'privacy' });
    const privacyContent = document.sections.flatMap((section) => section.paragraphs).join('\n');
    assert.doesNotMatch(privacyContent, /业务信息：您主动录入或确认的客户姓名/);
    clearAuthenticatedSession();
  } finally {
    if (previousPage === undefined) delete global.Page;
    else global.Page = previousPage;
  }
});
