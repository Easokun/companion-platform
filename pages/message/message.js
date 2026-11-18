// pages/message/message.js
const { getCategoriesWithServices, searchServices, loadAllFromServer } = require('../../utils/services.js')

Page({
  data: {
    statusBarHeight: 44,
    activeNav: 0,
    searchKeyword: '',
    searchResults: [],
    searchFocused: false,
    touchedId: null,
    // 分类数据（从统一配置加载）
    categories: []
  },

  // 防抖定时器
  _searchTimer: null,

  onLoad() {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({
      statusBarHeight: systemInfo.statusBarHeight,
      categories: getCategoriesWithServices()
    })
    this._loadData()
  },

  onShow() {
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 1 })
    }
    // 每次显示时刷新数据
    this._loadData()
  },

  _loadData() {
    loadAllFromServer().then(() => {
      this.setData({
        categories: getCategoriesWithServices()
      })
      // 如果当前选中的分类超出范围，重置为0
      if (this.data.activeNav >= this.data.categories.length) {
        this.setData({ activeNav: 0 })
      }
    })
  },

  onUnload() {
    if (this._searchTimer) {
      clearTimeout(this._searchTimer)
      this._searchTimer = null
    }
  },

  // 搜索聚焦
  onSearchFocus() {
    this.setData({ searchFocused: true })
  },

  // 搜索失焦
  onSearchBlur() {
    this.setData({ searchFocused: false })
  },

  // 搜索输入（防抖 300ms）
  onSearchInput(e) {
    const keyword = e.detail.value
    this.setData({ searchKeyword: keyword })
    // 清除之前的定时器
    if (this._searchTimer) {
      clearTimeout(this._searchTimer)
    }
    if (!keyword.trim()) {
      this.setData({ searchResults: [] })
      return
    }
    // 防抖延迟搜索
    this._searchTimer = setTimeout(() => {
      this.doSearch(keyword.trim())
    }, 300)
  },

  // 搜索确认
  onSearchConfirm(e) {
    const keyword = e.detail.value
    if (keyword.trim()) {
      // 清除防抖定时器
      if (this._searchTimer) {
        clearTimeout(this._searchTimer)
        this._searchTimer = null
      }
      this.doSearch(keyword.trim())
    }
  },

  // 执行搜索
  doSearch(keyword) {
    const results = searchServices(keyword)
    this.setData({ searchResults: results })
  },

  // 清空搜索
  clearSearch() {
    this.setData({ 
      searchKeyword: '',
      searchResults: []
    })
  },

  // 快捷搜索
  quickSearch(e) {
    const word = e.currentTarget.dataset.word
    this.setData({ searchKeyword: word })
    this.doSearch(word)
  },

  // 切换左侧分类
  switchNav(e) {
    const index = e.currentTarget.dataset.index
    this.setData({ activeNav: index })
    // 右侧内容滚动到顶部
    if (this.rightScrollView) {
      wx.pageScrollTo({ scrollTop: 0, duration: 200 })
    }
  },

  // 卡片触摸开始
  onTouchStart(e) {
    const id = e.currentTarget.dataset.id
    this.setData({ touchedId: id })
  },

  // 卡片触摸结束
  onTouchEnd() {
    setTimeout(() => {
      this.setData({ touchedId: null })
    }, 150)
  },

  // 点击服务跳转到下单页
  onServiceTap(e) {
    const service = e.currentTarget.dataset.service
    wx.navigateTo({
      url: `/pages/order/order?id=${service.id}&name=${encodeURIComponent(service.name)}&price=${service.price}&desc=${encodeURIComponent(service.desc)}&tag=${encodeURIComponent(service.tag)}&image=${encodeURIComponent(service.image)}&tagColor=${encodeURIComponent(service.tagColor)}`
    })
  }
})
