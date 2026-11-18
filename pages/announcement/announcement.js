// pages/announcement/announcement.js
const { announcementApi } = require('../../utils/api.js')

Page({
  data: {
    statusBarHeight: 44,
    announcements: [],
    loading: true
  },

  onLoad() {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({ statusBarHeight: systemInfo.statusBarHeight })
    this.loadAnnouncements()
  },

  loadAnnouncements() {
    this.setData({ loading: true })
    announcementApi.getLatest().then(res => {
      const list = (res && res.list) || []
      this.setData({
        announcements: list,
        loading: false
      })

      // 自动标记所有未读公告为已读
      list.forEach(ann => {
        if (!ann.isRead) {
          announcementApi.markRead(ann.id).catch(() => {})
        }
      })
    }).catch(() => {
      this.setData({ loading: false })
    })
  },

  onTapAnnouncement(e) {
    // 已在 loadAnnouncements 中标记已读，这里可扩展详情查看
  },

  goBack() {
    wx.navigateBack()
  }
})
