const demo = require('../../../mock/demo-control');
const {
  getQualificationView
} = require('../../../models/qualification-status');
const {
  QUALIFICATION_TYPES,
  DEFAULT_QUALIFICATION_FILE,
  createQualificationForm,
  normalizeQualificationFile,
  validateQualificationFile,
  validateQualificationUpdate
} = require('../../../models/qualification-update');

const DRAFT_KEY = 'lutai_qualification_update_draft';
const UPDATE_SOURCES = ['approved', 'rejected', 'expiring'];

function formatDateValue(date) {
  const pad = (value) => String(value).padStart(2, '0');

  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate())
  ].join('-');
}

function formatDateLabel(value) {
  const parts = String(value || '').split('-');

  if (parts.length !== 3) return value || '';
  return `${parts[0]}年${Number(parts[1])}月${Number(parts[2])}日`;
}

Page({
  data: {
    source: 'approved',
    rejectionReason: '',
    qualificationTypes: QUALIFICATION_TYPES,
    qualificationTypeIndex: 0,
    form: createQualificationForm(),
    expiryLabel: '',
    file: Object.assign({}, DEFAULT_QUALIFICATION_FILE),
    confirmed: false,
    invalidField: '',
    submitting: false,
    today: ''
  },

  onLoad(options = {}) {
    this.skipDraftPersistence = false;
    const source = UPDATE_SOURCES.indexOf(options.source) === -1
      ? 'approved'
      : options.source;
    const sourceStatus = getQualificationView(source);
    const draft = wx.getStorageSync(DRAFT_KEY) || {};
    const form = createQualificationForm(draft.form);
    const file = draft.file && draft.file.name
      ? draft.file
      : Object.assign({}, DEFAULT_QUALIFICATION_FILE);

    this.setData({
      source,
      rejectionReason: sourceStatus.reason || '',
      form,
      expiryLabel: formatDateLabel(form.expiresAt),
      file,
      qualificationTypeIndex: Math.max(
        0,
        QUALIFICATION_TYPES.indexOf(form.qualificationType)
      ),
      confirmed: draft.confirmed === true,
      today: formatDateValue(new Date())
    });
  },

  onHide() {
    if (!this.skipDraftPersistence) this.persistDraft();
  },

  handleBack() {
    this.persistDraft();

    if (getCurrentPages().length > 1) {
      wx.navigateBack({ delta: 1 });
      return;
    }

    wx.redirectTo({
      url: `/pages/qualification/status/index?state=${this.data.source}`
    });
  },

  onFieldInput(event) {
    const field = event.currentTarget.dataset.field;
    const patch = {};

    patch[`form.${field}`] = event.detail.value;
    if (this.data.invalidField === field) patch.invalidField = '';
    this.setData(patch);
  },

  onQualificationTypeChange(event) {
    const index = Number(event.detail.value) || 0;

    this.setData({
      qualificationTypeIndex: index,
      'form.qualificationType': QUALIFICATION_TYPES[index],
      invalidField: ''
    });
    this.persistDraft();
  },

  onExpiryChange(event) {
    this.setData({
      'form.expiresAt': event.detail.value,
      expiryLabel: formatDateLabel(event.detail.value),
      invalidField: ''
    });
    this.persistDraft();
  },

  chooseQualificationFile() {
    wx.showActionSheet({
      itemList: ['从聊天文件选择', '从相册选择'],
      success: ({ tapIndex }) => {
        if (tapIndex === 0) {
          this.chooseMessageFile();
        } else {
          this.chooseImageFile();
        }
      }
    });
  },

  chooseMessageFile() {
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      extension: ['pdf', 'jpg', 'jpeg', 'png'],
      success: ({ tempFiles }) => {
        const selected = tempFiles && tempFiles[0];
        if (selected) this.acceptFile(selected);
      }
    });
  },

  chooseImageFile() {
    if (!wx.chooseMedia) {
      wx.showToast({
        title: '当前微信版本暂不支持相册选择',
        icon: 'none'
      });
      return;
    }

    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      success: ({ tempFiles }) => {
        const selected = tempFiles && tempFiles[0];
        if (!selected) return;

        this.acceptFile({
          name: `营业执照.${selected.fileType || 'jpg'}`,
          size: selected.size,
          path: selected.tempFilePath
        });
      }
    });
  },

  acceptFile(rawFile) {
    const file = normalizeQualificationFile(rawFile);
    const validation = validateQualificationFile(file);

    if (!validation.valid) {
      this.setData({ invalidField: 'file' });
      wx.showToast({
        title: validation.message,
        icon: 'none'
      });
      return;
    }

    this.setData({
      file,
      invalidField: ''
    });
    this.persistDraft();
    wx.showToast({
      title: '文件已更新',
      icon: 'success'
    });
  },

  previewFile() {
    const file = this.data.file;

    if (!file.path) {
      wx.showModal({
        title: file.name,
        content: `已上传 · ${file.sizeLabel}\n演示环境暂不打开历史资质文件。`,
        showCancel: false,
        confirmText: '知道了'
      });
      return;
    }

    if (file.kind === 'image') {
      wx.previewImage({
        current: file.path,
        urls: [file.path]
      });
      return;
    }

    wx.openDocument({
      filePath: file.path,
      showMenu: true,
      fail: () => {
        wx.showToast({
          title: '文件预览失败',
          icon: 'none'
        });
      }
    });
  },

  toggleConfirmation() {
    this.setData({
      confirmed: !this.data.confirmed,
      invalidField: ''
    });
    this.persistDraft();
  },

  submitQualification() {
    const validation = validateQualificationUpdate(
      this.data.form,
      this.data.file,
      this.data.confirmed,
      this.data.today
    );

    if (!validation.valid) {
      this.setData({ invalidField: validation.field });
      wx.showToast({
        title: validation.message,
        icon: 'none'
      });
      return;
    }

    wx.showModal({
      title: '确认提交审核',
      content: '提交后将进入资质审核流程，审核期间资料不可修改。',
      confirmText: '确认提交',
      success: ({ confirm }) => {
        if (!confirm || this.data.submitting) return;

        this.setData({ submitting: true });
        demo.setDemoSession(Object.assign({}, demo.getDemoSession(), {
          qualificationStatus: 'reviewing'
        }));
        this.skipDraftPersistence = true;
        wx.removeStorageSync(DRAFT_KEY);
        wx.showToast({
          title: '提交成功',
          icon: 'success',
          duration: 900
        });

        setTimeout(() => {
          wx.reLaunch({
            url: '/pages/qualification/status/index?state=reviewing'
          });
        }, 500);
      }
    });
  },

  persistDraft() {
    wx.setStorageSync(DRAFT_KEY, {
      form: this.data.form,
      file: this.data.file,
      confirmed: this.data.confirmed
    });
  }
});
