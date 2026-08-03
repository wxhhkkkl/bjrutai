const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const projectRoot = path.resolve(__dirname, '../..');
const tabPages = [
  'pages/home/index.wxml',
  'pages/customers/index.wxml',
  'pages/contribution/index.wxml',
  'pages/profile/index.wxml'
];
const interactiveRoots = ['pages', 'components', 'custom-tab-bar'];

function collectFiles(relativePath, extension, files = []) {
  const absolutePath = path.join(projectRoot, relativePath);
  const entries = fs.readdirSync(absolutePath, { withFileTypes: true });

  for (const entry of entries) {
    const childPath = path.join(relativePath, entry.name);

    if (entry.isDirectory()) {
      collectFiles(childPath, extension, files);
    } else if (entry.name.endsWith(extension)) {
      files.push(childPath);
    }
  }

  return files;
}

test('all tab pages use the shared app header', () => {
  for (const page of tabPages) {
    const source = fs.readFileSync(path.join(projectRoot, page), 'utf8');

    assert.match(source, /<app-header\b/, page);
    assert.doesNotMatch(source, /\bsafe-top\b/, page);
  }
});

test('custom tab bar keeps content and safe area in separate layers', () => {
  const markup = fs.readFileSync(
    path.join(projectRoot, 'custom-tab-bar/index.wxml'),
    'utf8'
  );
  const styles = fs.readFileSync(
    path.join(projectRoot, 'custom-tab-bar/index.wxss'),
    'utf8'
  );

  assert.match(markup, /tabbar-content/);
  assert.match(markup, /tabbar-safe-area/);
  assert.match(styles, /\.tabbar-content[\s\S]*height:\s*132rpx/);
  assert.match(styles, /\.tabbar-safe-area[\s\S]*env\(safe-area-inset-bottom\)/);
});

test('customer tab uses the approved overview slice and real controls', () => {
  const source = fs.readFileSync(
    path.join(projectRoot, 'pages/customers/index.wxml'),
    'utf8'
  );

  assert.match(source, /customer-overview-card\.png/);
  assert.match(source, /bindinput="onSearch"/);
  assert.match(source, /bindtap="selectFilter"/);
  assert.match(source, /bindtap="bindCustomer"/);
  assert.match(source, /class="customer-card\b/);
});

test('customer detail shares one functional structure across three tabs', () => {
  const source = fs.readFileSync(
    path.join(projectRoot, 'pages/customer-detail/index.wxml'),
    'utf8'
  );
  const appConfig = JSON.parse(
    fs.readFileSync(path.join(projectRoot, 'app.json'), 'utf8')
  );

  assert.ok(appConfig.pages.includes('pages/customer-detail/index'));
  assert.match(source, /<flow-navigation\b/);
  assert.match(source, /class="customer-hero"/);
  assert.match(source, /currentTab === 'info'/);
  assert.match(source, /currentTab === 'service'/);
  assert.match(source, /bindtap="selectTab"/);
  assert.match(source, /bindtap="selectContributionFilter"/);
  assert.match(source, /bindtap="contactCustomer"/);
  assert.match(source, /bindtap="recordFollowup"/);
  assert.match(source, /class="customer-action-bar"/);
});

test('followup record page uses the approved real form controls', () => {
  const source = fs.readFileSync(
    path.join(projectRoot, 'pages/followup-record/index.wxml'),
    'utf8'
  );
  const appConfig = JSON.parse(
    fs.readFileSync(path.join(projectRoot, 'app.json'), 'utf8')
  );

  assert.ok(appConfig.pages.includes('pages/followup-record/index'));
  assert.match(source, /<flow-navigation\b/);
  assert.match(source, /bindtap="selectMethod"/);
  assert.match(source, /bindtap="selectResult"/);
  assert.match(source, /bindinput="onContentInput"/);
  assert.match(source, /mode="date"/);
  assert.match(source, /mode="time"/);
  assert.match(source, /bindtap="saveDraft"/);
  assert.match(source, /bindtap="saveFollowup"/);
  assert.doesNotMatch(source, /<textarea\b[^>]*\bfocus=/s);
});

test('customer edit page keeps display rows and real edit controls', () => {
  const source = fs.readFileSync(
    path.join(projectRoot, 'pages/customer-edit/index.wxml'),
    'utf8'
  );
  const appConfig = JSON.parse(
    fs.readFileSync(path.join(projectRoot, 'app.json'), 'utf8')
  );

  assert.ok(appConfig.pages.includes('pages/customer-edit/index'));
  assert.match(source, /<flow-navigation\b/);
  assert.match(source, /class="edit-customer-summary"/);
  assert.match(source, /bindtap="openEditor"/);
  assert.match(source, /bindinput="onNoteInput"/);
  assert.match(source, /bindtap="saveChanges"/);
  assert.match(source, /bindtap="cancelEdit"/);
  assert.match(source, /class="edit-action-bar"/);
  assert.doesNotMatch(source, /<input\b[^>]*\bfocus=/s);
});

test('customer analysis uses two echarts and real period controls', () => {
  const source = fs.readFileSync(
    path.join(projectRoot, 'pages/customer-analysis/index.wxml'),
    'utf8'
  );
  const pageConfig = JSON.parse(
    fs.readFileSync(
      path.join(projectRoot, 'pages/customer-analysis/index.json'),
      'utf8'
    )
  );
  const appConfig = JSON.parse(
    fs.readFileSync(path.join(projectRoot, 'app.json'), 'utf8')
  );

  assert.ok(appConfig.pages.includes('pages/customer-analysis/index'));
  assert.equal(
    pageConfig.usingComponents['ec-canvas'],
    '/ec-canvas/ec-canvas'
  );
  assert.match(source, /<flow-navigation\b/);
  assert.equal((source.match(/<ec-canvas\b/g) || []).length, 2);
  assert.match(source, /bindtap="selectPeriod"/);
  assert.match(source, /bindchange="onDateChange"/);
  assert.match(source, /bindtap="openAttention"/);
  assert.match(source, /class="analysis-update"/);
});

test('contribution detail uses approved summary and grouped filters', () => {
  const source = fs.readFileSync(
    path.join(projectRoot, 'pages/contribution-detail/index.wxml'),
    'utf8'
  );
  const appConfig = JSON.parse(
    fs.readFileSync(path.join(projectRoot, 'app.json'), 'utf8')
  );

  assert.ok(appConfig.pages.includes('pages/contribution-detail/index'));
  assert.match(source, /<flow-navigation\b/);
  assert.match(source, /contribution-detail-hero\.png/);
  assert.match(source, /fields="month"/);
  assert.match(source, /bindtap="selectStatus"/);
  assert.match(source, /bindtap="openCategoryFilter"/);
  assert.match(source, /bindtap="openContribution"/);
  assert.match(source, /class="contribution-detail-notice"/);
  assert.ok(
    fs.existsSync(
      path.join(
        projectRoot,
        'assets/images/contribution-detail-hero.png'
      )
    )
  );
});

test('promotion code page uses the approved QR and real sharing controls', () => {
  const source = fs.readFileSync(
    path.join(projectRoot, 'pages/promotion-code/index.wxml'),
    'utf8'
  );
  const appConfig = JSON.parse(
    fs.readFileSync(path.join(projectRoot, 'app.json'), 'utf8')
  );

  assert.ok(appConfig.pages.includes('pages/promotion-code/index'));
  assert.match(source, /<flow-navigation\b/);
  assert.match(source, /promotion-qr\.png|profile\.qrImage/);
  assert.match(source, /bindtap="savePromotionCode"/);
  assert.match(source, /open-type="share"/);
  assert.match(source, /class="promotion-steps"/);
  assert.match(source, /class="promotion-notice"/);
  assert.ok(
    fs.existsSync(
      path.join(projectRoot, 'assets/images/promotion-qr.png')
    )
  );
});

test('login authorization uses the approved hero and real authorization controls', () => {
  const source = fs.readFileSync(
    path.join(projectRoot, 'pages/auth/login/index.wxml'),
    'utf8'
  );

  assert.match(source, /<app-header\b/);
  assert.match(source, /login-security-hero\.png/);
  assert.match(source, /bindtap="login"/);
  assert.match(source, /open-type="getPhoneNumber"/);
  assert.match(source, /bindgetphonenumber="authorizePhone"/);
  assert.match(source, /bindtap="toggleAgreement"/);
  assert.match(source, /bindtap="openDocument"/);
  assert.ok(
    fs.existsSync(
      path.join(projectRoot, 'assets/images/login-security-hero.png')
    )
  );
});

test('profile setup uses stable inputs and submits the approved first step', () => {
  const source = fs.readFileSync(
    path.join(projectRoot, 'pages/auth/profile-setup/index.wxml'),
    'utf8'
  );

  assert.match(source, /<flow-navigation\b/);
  assert.match(source, /账号初始化/);
  assert.match(source, /bindinput="onFieldInput"/);
  assert.match(source, /data-field="name"/);
  assert.match(source, /data-field="organization"/);
  assert.match(source, /bindtap="toggleConfirmation"/);
  assert.match(source, /bindtap="submitProfile"/);
  assert.match(source, /class="profile-submit-bar"/);
  assert.doesNotMatch(source, /<input\b[^>]*\bfocus=/s);
});

test('account profile matches the approved editable account design', () => {
  const source = fs.readFileSync(
    path.join(projectRoot, 'pages/account-profile/index.wxml'),
    'utf8'
  );
  const styles = fs.readFileSync(
    path.join(projectRoot, 'pages/account-profile/index.wxss'),
    'utf8'
  );
  const appConfig = JSON.parse(
    fs.readFileSync(path.join(projectRoot, 'app.json'), 'utf8')
  );

  assert.ok(appConfig.pages.includes('pages/account-profile/index'));
  assert.match(source, /<flow-navigation\b/);
  assert.match(source, /编辑账号资料/);
  assert.match(source, /bindinput="onFieldInput"/);
  assert.match(source, /bindtap="chooseAvatar"/);
  assert.match(source, /open-type="getPhoneNumber"/);
  assert.match(source, /bindgetphonenumber="authorizePhone"/);
  assert.match(source, /bindtap="saveProfile"/);
  assert.match(source, /class="account-save-bar"/);
  assert.match(styles, /\.account-save-bar[\s\S]*env\(safe-area-inset-bottom\)/);
  assert.doesNotMatch(source, /<input\b[^>]*\bfocus=/s);
});

test('help feedback matches the approved functional design', () => {
  const source = fs.readFileSync(
    path.join(projectRoot, 'pages/help-feedback/index.wxml'),
    'utf8'
  );
  const styles = fs.readFileSync(
    path.join(projectRoot, 'pages/help-feedback/index.wxss'),
    'utf8'
  );
  const appConfig = JSON.parse(
    fs.readFileSync(path.join(projectRoot, 'app.json'), 'utf8')
  );

  assert.ok(appConfig.pages.includes('pages/help-feedback/index'));
  assert.match(source, /<flow-navigation\b/);
  assert.match(source, /bindtap="openFaq"/);
  assert.match(source, /bindtap="selectFeedbackType"/);
  assert.match(source, /bindinput="onContentInput"/);
  assert.match(source, /bindtap="chooseScreenshots"/);
  assert.match(source, /bindtap="previewScreenshot"/);
  assert.match(source, /catchtap="removeScreenshot"/);
  assert.match(source, /open-type="contact"/);
  assert.match(source, /bindcontact="handleContact"/);
  assert.match(source, /bindtap="submitFeedback"/);
  assert.match(source, /class="help-submit-bar"/);
  assert.match(styles, /\.help-submit-bar[\s\S]*env\(safe-area-inset-bottom\)/);
  assert.doesNotMatch(source, /<textarea\b[^>]*\bfocus=/s);
});

test('contribution tab uses approved assets and echarts-for-weixin', () => {
  const markup = fs.readFileSync(
    path.join(projectRoot, 'pages/contribution/index.wxml'),
    'utf8'
  );
  const pageConfig = JSON.parse(
    fs.readFileSync(
      path.join(projectRoot, 'pages/contribution/index.json'),
      'utf8'
    )
  );

  assert.match(markup, /contribution-banner-visual\.png/);
  assert.match(markup, /<ec-canvas\b/);
  assert.match(markup, /bindtap="selectPeriod"/);
  assert.match(markup, /class="composition-card"/);
  assert.match(markup, /class="detail-row\b/);
  assert.equal(
    pageConfig.usingComponents['ec-canvas'],
    '/ec-canvas/ec-canvas'
  );

  for (const file of [
    'ec-canvas/ec-canvas.js',
    'ec-canvas/ec-canvas.wxml',
    'ec-canvas/echarts.js',
    'ec-canvas/LICENSE'
  ]) {
    assert.ok(fs.existsSync(path.join(projectRoot, file)), file);
  }
});

test('profile tab uses approved assets and complete service controls', () => {
  const source = fs.readFileSync(
    path.join(projectRoot, 'pages/profile/index.wxml'),
    'utf8'
  );

  assert.match(source, /profile-hero-visual\.png/);
  assert.match(source, /profile-avatar\.png/);
  assert.match(source, /class="profile-service-grid"/);
  assert.match(source, /class="profile-account-card"/);
  assert.match(source, /bindtap="logout"/);
  assert.match(source, /data-id="profile"/);

  for (const file of [
    'profile-promo-icon.png',
    'profile-records-icon.png',
    'profile-contribution-icon.png',
    'profile-notification-icon.png',
    'profile-account-icon.png',
    'profile-help-icon.png',
    'profile-privacy-icon.png'
  ]) {
    assert.ok(
      fs.existsSync(path.join(projectRoot, 'assets/images', file)),
      file
    );
  }
});

test('customer binding is a single stateful three-step flow', () => {
  const source = fs.readFileSync(
    path.join(projectRoot, 'pages/customer-binding/index.wxml'),
    'utf8'
  );
  const appConfig = JSON.parse(
    fs.readFileSync(path.join(projectRoot, 'app.json'), 'utf8')
  );

  assert.ok(appConfig.pages.includes('pages/customer-binding/index'));
  assert.match(source, /<flow-navigation\b/);
  assert.match(source, /<binding-progress\b/);
  assert.match(source, /step === 1/);
  assert.match(source, /step === 2/);
  assert.match(source, /bindtap="nextStep"/);
  assert.match(source, /bindtap="submitBinding"/);
  assert.match(source, /bindtap="continueBinding"/);
  assert.match(source, /bindtap="goToStepOne"/);
  assert.doesNotMatch(
    source,
    /<input\b[^>]*\bfocus="\{\{invalidField ===/s,
    'controlled focus must not blur inputs during bindinput setData'
  );

  for (const file of [
    'components/flow-navigation/index.js',
    'components/binding-progress/index.js',
    'models/customer-binding.js'
  ]) {
    assert.ok(fs.existsSync(path.join(projectRoot, file)), file);
  }
});

test('binding records page uses the approved functional layout', () => {
  const source = fs.readFileSync(
    path.join(projectRoot, 'pages/binding-records/index.wxml'),
    'utf8'
  );
  const appConfig = JSON.parse(
    fs.readFileSync(path.join(projectRoot, 'app.json'), 'utf8')
  );

  assert.ok(appConfig.pages.includes('pages/binding-records/index'));
  assert.match(source, /<flow-navigation\b/);
  assert.match(source, /class="records-overview"/);
  assert.match(source, /bindinput="onSearch"/);
  assert.match(source, /bindtap="selectFilter"/);
  assert.match(source, /bindtap="showStatusDescription"/);
  assert.match(source, /bindtap="continueBinding"/);
  assert.match(source, /class="record-card tap-target"/);
});

test('binding result page shares one structure across three approved states', () => {
  const source = fs.readFileSync(
    path.join(projectRoot, 'pages/binding-result/index.wxml'),
    'utf8'
  );
  const appConfig = JSON.parse(
    fs.readFileSync(path.join(projectRoot, 'app.json'), 'utf8')
  );

  assert.ok(appConfig.pages.includes('pages/binding-result/index'));
  assert.match(source, /<flow-navigation\b/);
  assert.match(source, /<binding-progress\b/);
  assert.match(source, /state === 'matching'/);
  assert.match(source, /state === 'bound'/);
  assert.match(source, /bindtap="modifyCustomer"/);
  assert.match(source, /bindtap="returnToRecords"/);
  assert.match(source, /bindtap="continueBinding"/);

  for (const file of [
    'binding-result-matching.png',
    'binding-result-bound.png',
    'binding-result-failed.png'
  ]) {
    assert.ok(
      fs.existsSync(path.join(projectRoot, 'assets/images', file)),
      file
    );
  }
});

test('all business tap targets use the shared press feedback', () => {
  const markupFiles = interactiveRoots.flatMap((root) =>
    collectFiles(root, '.wxml')
  );
  const tapTargetPattern =
    /<(?:view|text|button)\b[^>]*\b(?:bindtap|bind:tap|catchtap)="[^"]+"[^>]*>/gs;

  for (const file of markupFiles) {
    const source = fs.readFileSync(path.join(projectRoot, file), 'utf8');
    const tapTargets = source.match(tapTargetPattern) || [];

    for (const target of tapTargets) {
      assert.match(target, /\bclass="[^"]*\btap-target\b[^"]*"/, file);
      assert.match(target, /\bhover-class="tap-feedback"/, file);
    }
  }
});

test('all literal Vant icon names exist in the installed icon font', () => {
  const iconStyles = fs.readFileSync(
    path.join(
      projectRoot,
      'miniprogram_npm/@vant/weapp/icon/index.wxss'
    ),
    'utf8'
  );
  const markupFiles = interactiveRoots.flatMap((root) =>
    collectFiles(root, '.wxml')
  );
  const iconPattern = /<van-icon\b[^>]*\bname="([a-z0-9-]+)"[^>]*\/>/gs;

  for (const file of markupFiles) {
    const source = fs.readFileSync(path.join(projectRoot, file), 'utf8');

    for (const match of source.matchAll(iconPattern)) {
      assert.match(
        iconStyles,
        new RegExp(`\\.van-icon-${match[1]}:before`),
        `${file}: ${match[1]}`
      );
    }
  }
});

test('shared press feedback is available to pages and interactive components', () => {
  const globalStyles = fs.readFileSync(
    path.join(projectRoot, 'app.wxss'),
    'utf8'
  );
  const interactionStyles = fs.readFileSync(
    path.join(projectRoot, 'styles/interactions.wxss'),
    'utf8'
  );

  assert.match(globalStyles, /@import "\.\/styles\/interactions\.wxss"/);
  assert.match(interactionStyles, /\.tap-target/);
  assert.match(interactionStyles, /\.tap-feedback/);

  for (const component of [
    'components/app-header/index.wxss',
    'components/navigation-bar/navigation-bar.wxss',
    'components/page-state/index.wxss',
    'custom-tab-bar/index.wxss'
  ]) {
    const source = fs.readFileSync(path.join(projectRoot, component), 'utf8');

    assert.match(source, /styles\/interactions\.wxss/, component);
  }
});
