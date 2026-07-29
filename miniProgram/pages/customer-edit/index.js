const { getCustomerDetail } = require('../../models/customer-detail');
const { BINDING_RECORDS } = require('../../models/binding-records');
const {
  EDITABLE_CUSTOMER_FIELDS,
  createCustomerEditForm,
  validateEditField,
  validateCustomerEditForm
} = require('../../models/customer-edit');

Page({
  data: {
    customer: getCustomerDetail('customer-001'),
    form: createCustomerEditForm(getCustomerDetail('customer-001')),
    noteLength: 0,
    editorVisible: false,
    editorField: '',
    editorTitle: '',
    editorValue: '',
    editorType: 'text',
    editorMaxlength: 30,
    editorSensitive: false
  },

  onLoad(options = {}) {
    let customer = getCustomerDetail(options.id);

    if (options.recordId) {
      const record = BINDING_RECORDS.find(
        (item) => item.id === options.recordId
      );

      if (record) {
        customer = {
          ...customer,
          name: record.name,
          phone: record.phone,
          idCard: record.idCard
        };
      }
    }

    this.setData({
      customer,
      form: createCustomerEditForm(customer),
      noteLength: String(customer.note || '').length
    });
  },

  openEditor(e) {
    const field = e.currentTarget.dataset.field;
    const config = EDITABLE_CUSTOMER_FIELDS[field];

    if (!config) return;

    this.setData({
      editorVisible: true,
      editorField: field,
      editorTitle: config.title,
      editorValue: this.data.form[field],
      editorType: config.type,
      editorMaxlength: config.maxlength,
      editorSensitive: config.sensitive
    });
  },

  onEditorInput(e) {
    this.setData({ editorValue: e.detail.value });
  },

  confirmEditor() {
    const result = validateEditField(
      this.data.editorField,
      this.data.editorValue
    );

    if (!result.valid) {
      wx.showToast({ title: result.message, icon: 'none' });
      return;
    }

    this.setData({
      [`form.${this.data.editorField}`]: result.value,
      editorVisible: false
    });
  },

  closeEditor() {
    this.setData({ editorVisible: false });
  },

  onNoteInput(e) {
    const note = e.detail.value;

    this.setData({
      'form.note': note,
      noteLength: note.length
    });
  },

  saveChanges() {
    const result = validateCustomerEditForm(this.data.form);

    if (!result.valid) {
      wx.showToast({ title: result.message, icon: 'none' });
      return;
    }

    this.setData({ form: result.value });
    wx.showToast({
      title: '资料已更新',
      icon: 'success'
    });
  },

  cancelEdit() {
    wx.navigateBack();
  },

  handleBack() {
    wx.navigateBack();
  }
});
