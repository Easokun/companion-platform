// pages/order/order.js
const { favoriteApi } = require('../../utils/api.js')
const { allServices, getServiceById } = require('../../utils/services.js')

Page({
  data: {
    statusBarHeight: 44,
    selectedService: null,
    isFavorited: false,
    // 从统一配置加载服务列表
    serviceList: allServices
  },

  onLoad(options) {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({ statusBarHeight: systemInfo.statusBarHeight })

    // 接收首页传过来的服务ID，优先从统一配置取
    if (options.id) {
      let service = getServiceById(options.id)
      if (!service) {
        // 兼容旧的URL传参方式
        const price = parseFloat(options.price) || 0
        service = {
          id: options.id,
          name: decodeURIComponent(options.name),
          price: price,
          icon: decodeURIComponent(options.icon || '🎮'),
          desc: decodeURIComponent(options.desc),
          tag: decodeURIComponent(options.tag),
          image: decodeURIComponent(options.image || '/images/logo.png'),
          tagColor: options.tagColor ? decodeURIComponent(options.tagColor) : 'linear-gradient(90deg, #7B61FF, #A78BFA)'
        }
      } else {
        service = { ...service, price: parseFloat(service.price) || 0 }
      }
      this.setData({ selectedService: service })
      // 检查是否已收藏（异步）
      favoriteApi.isFavorited(service.id).then(isFavorited => {
        this.setData({ isFavorited: isFavorited })
      })
    }
  },

  // 在下单页直接选择服务
  onSelectService(e) {
    const index = e.currentTarget.dataset.index
    const service = this.data.serviceList[index]
    const price = parseFloat(service.price) || 0
    const selectedService = { ...service, price: price }
    this.setData({ selectedService: selectedService })
    // 检查收藏状态（异步）
    favoriteApi.isFavorited(service.id).then(isFavorited => {
      this.setData({ isFavorited: isFavorited })
    })
  },

  // 切换服务（已选状态下重新选）
  onChangeService() {
    this.setData({ selectedService: null, isFavorited: false })
  },

  // 提交订单 - 跳转到确认订单页
  onSubmit() {
    if (!this.data.selectedService) {
      wx.showToast({ title: '请先选择服务', icon: 'none' })
      return
    }
    const s = this.data.selectedService
    wx.navigateTo({
      url: `/pages/confirmOrder/confirmOrder?id=${s.id}&name=${encodeURIComponent(s.name)}&price=${s.price}&icon=${encodeURIComponent(s.icon || '🎮')}&desc=${encodeURIComponent(s.desc)}&tag=${encodeURIComponent(s.tag)}&tagColor=${encodeURIComponent(s.tagColor || '')}&image=${encodeURIComponent(s.image || '/images/logo.png')}`
    })
  },

  // 联系客服
  onContactKefu() {
    wx.showToast({ title: '联系客服', icon: 'none' })
  },

  // 收藏/取消收藏
  onFavoriteService() {
    const service = this.data.selectedService
    if (!service) return
    favoriteApi.isFavorited(service.id).then(favorited => {
      if (favorited) {
        favoriteApi.removeFavorite(service.id).then(() => {
          this.setData({ isFavorited: false })
          wx.showToast({ title: '已取消收藏', icon: 'none' })
        })
      } else {
        favoriteApi.addFavorite(service).then(() => {
          this.setData({ isFavorited: true })
          wx.showToast({ title: '已收藏', icon: 'success' })
        })
      }
    })
  },

  // 返回上一页
  goBack() {
    wx.navigateBack()
  }
})
