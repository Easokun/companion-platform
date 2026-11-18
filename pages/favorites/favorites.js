// pages/favorites/favorites.js
const { favoriteApi, userApi } = require('../../utils/api.js')

Page({
  data: {
    statusBarHeight: 44,
    favorites: [],
    isLogin: false
  },

  onLoad() {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({ statusBarHeight: systemInfo.statusBarHeight })
  },

  onShow() {
    this.checkLoginAndLoad()
  },

  // 检查登录并加载数据
  checkLoginAndLoad() {
    userApi.getCurrentUser().then(user => {
      if (!user || !user.userId) {
        this.setData({ isLogin: false, favorites: [] })
        return
      }
      this.setData({ isLogin: true })
      this.loadFavorites()
    })
  },

  loadFavorites() {
    favoriteApi.getFavorites().then(favorites => {
      this.setData({ favorites })
    })
  },

  goBack() {
    wx.navigateBack()
  },

  // 点击收藏卡片进入下单页
  onFavoriteTap(e) {
    const index = e.currentTarget.dataset.index
    const service = this.data.favorites[index]
    wx.navigateTo({
      url: `/pages/order/order?id=${service.id}&name=${encodeURIComponent(service.name)}&price=${service.price}&icon=${encodeURIComponent(service.icon || '🎮')}&desc=${encodeURIComponent(service.desc || '')}&tag=${encodeURIComponent(service.tag || '热门')}&image=${encodeURIComponent(service.image || '/images/logo.png')}`
    })
  },

  // 取消收藏
  onRemoveFavorite(e) {
    const index = e.currentTarget.dataset.index
    const service = this.data.favorites[index]
    wx.showModal({
      title: '提示',
      content: '确定取消收藏该服务？',
      success: (res) => {
        if (res.confirm) {
          favoriteApi.removeFavorite(service.id).then(() => {
            this.loadFavorites()
            wx.showToast({ title: '已取消收藏', icon: 'none' })
          })
        }
      }
    })
  }
})
