// pages/index/index.js
const { getHotTagsWithServices, loadAllFromServer } = require('../../utils/services.js')

Page({
  data: {
    statusBarHeight: 44,
    noticeText: '🎉 今日公告：警告！！！未成年禁止下单！！！',
    noticeAnimation: {},
    activeCard: -1,
    // 火热标签（从统一配置加载）
    activeTagIndex: 0,
    hotTags: [],
    // 轮播图
    banners: [],
    // 功能弹窗
    showFeatureModal: false,
    featureModalType: '',
    featureModalTitle: '',
    featureModalImage: '',
    featureModalContent: ''
  },

  _noticeTimer: null,
  _noticeResetTimer: null,
  _cardTouchTimer: null,

  onLoad() {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({
      statusBarHeight: systemInfo.statusBarHeight,
      hotTags: getHotTagsWithServices()
    })
    this.startNoticeScroll()
    this._loadData()
  },

  onShow() {
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 0 })
    }
    // 每次显示首页时刷新数据
    this._loadData()
  },

  _loadData() {
    loadAllFromServer().then((result) => {
      const { banners } = result
      this.setData({
        hotTags: getHotTagsWithServices(),
        banners: banners || []
      })
      // 如果当前选中的标签超出了范围，重置为0
      if (this.data.activeTagIndex >= this.data.hotTags.length) {
        this.setData({ activeTagIndex: 0 })
      }
    })
  },

  startNoticeScroll() {
    const textWidth = 600
    const screenWidth = wx.getSystemInfoSync().windowWidth
    const animation = wx.createAnimation({
      duration: 12000,
      timingFunction: 'linear',
      delay: 500
    })
    animation.translateX(-(textWidth + screenWidth)).step()
    this.setData({
      noticeAnimation: animation.export()
    })
    this._noticeTimer = setInterval(() => {
      const ani = wx.createAnimation({
        duration: 0,
        timingFunction: 'linear'
      })
      ani.translateX(screenWidth).step()
      this.setData({ noticeAnimation: ani.export() })
      
      this._noticeResetTimer = setTimeout(() => {
        const ani2 = wx.createAnimation({
          duration: 12000,
          timingFunction: 'linear'
        })
        ani2.translateX(-(textWidth + screenWidth)).step()
        this.setData({ noticeAnimation: ani2.export() })
      }, 50)
    }, 12500)
  },

  onUnload() {
    if (this._noticeTimer) {
      clearInterval(this._noticeTimer)
      this._noticeTimer = null
    }
    if (this._noticeResetTimer) {
      clearTimeout(this._noticeResetTimer)
      this._noticeResetTimer = null
    }
    if (this._cardTouchTimer) {
      clearTimeout(this._cardTouchTimer)
      this._cardTouchTimer = null
    }
  },

  // 轮播图点击
  onBannerTap(e) {
    const linkUrl = e.currentTarget.dataset.link
    if (linkUrl) {
      // 如果有跳转链接，处理跳转（小程序内跳转到对应页面）
      wx.navigateTo({
        url: linkUrl,
        fail: () => {
          wx.showToast({ title: '链接无效', icon: 'none' })
        }
      })
    }
  },

  onFeatureTap(e) {
    const type = e.currentTarget.dataset.type
    const modalConfig = {
      service: {
        title: '人工客服',
        type: 'image',
        image: '/images/logo.png'
      },
      guide: {
        title: '下单必看',
        type: 'text',
        content: '敬请期待'
      },
      flow: {
        title: '购买流程',
        type: 'text',
        content: '敬请期待'
      },
      join: {
        title: '考核入驻',
        type: 'image',
        image: '/images/logo.png'
      }
    }
    const config = modalConfig[type]
    if (config) {
      this.setData({
        showFeatureModal: true,
        featureModalType: config.type,
        featureModalTitle: config.title,
        featureModalImage: config.image || '',
        featureModalContent: config.content || ''
      })
    }
  },

  // 关闭功能弹窗
  closeFeatureModal() {
    this.setData({ showFeatureModal: false })
  },

  // 阻止弹窗内容区域冒泡
  stopModalPropagation() {},

  // 服务卡片点击 —— 跳转到下单页，把服务信息带过去
  onServiceTap(e) {
    const index = e.currentTarget.dataset.index
    const service = this.data.hotTags[this.data.activeTagIndex].services[index]
    wx.navigateTo({
      url: `/pages/order/order?id=${service.id}&name=${encodeURIComponent(service.name)}&price=${service.price}&desc=${encodeURIComponent(service.desc)}&tag=${encodeURIComponent(service.tag)}&image=${encodeURIComponent(service.image)}`
    })
  },

  // 点击火热标签 —— 切换下方服务卡片
  onTagTap(e) {
    const index = e.currentTarget.dataset.index
    this.setData({ 
      activeTagIndex: index,
      activeCard: -1
    })
  },

  onCardTouchStart(e) {
    this.setData({
      activeCard: e.currentTarget.dataset.index
    })
  },

  onCardTouchEnd() {
    this._cardTouchTimer = setTimeout(() => {
      this.setData({ activeCard: -1 })
    }, 150)
  },

  goMore() {
    wx.showToast({
      title: '查看更多服务',
      icon: 'none'
    })
  }
})
