// pages/feedback/feedback.js
Page({
  data: {
    statusBarHeight: 44,
    feedbackType: 0, // 0=功能建议 1=Bug反馈 2=其他
    typeOptions: ['功能建议', 'Bug反馈', '其他'],
    content: '',
    contact: ''
  },

  onLoad() {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({ statusBarHeight: systemInfo.statusBarHeight })
  },

  goBack() {
    wx.navigateBack()
  },

  // 选择反馈类型
  onTypeTap(e) {
    const index = e.currentTarget.dataset.index
    this.setData({ feedbackType: index })
  },

  // 内容输入
  onContentInput(e) {
    this.setData({ content: e.detail.value })
  },

  // 联系方式输入
  onContactInput(e) {
    this.setData({ contact: e.detail.value })
  },

  // 提交反馈
  submitFeedback() {
    const { content, contact, feedbackType, typeOptions } = this.data
    if (!content.trim()) {
      wx.showToast({ title: '请输入反馈内容', icon: 'none' })
      return
    }

    wx.showLoading({ title: '提交中...' })

    // 模拟提交
    setTimeout(() => {
      wx.hideLoading()
      wx.showToast({
        title: '反馈已提交',
        icon: 'success',
        duration: 2000
      })
      setTimeout(() => {
        wx.navigateBack()
      }, 1500)
    }, 1000)
  }
})
