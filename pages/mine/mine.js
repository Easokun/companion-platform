// pages/mine/mine.js
const { userApi, orderApi, favoriteApi, applyApi, escortApi, announcementApi, utils } = require('../../utils/api.js')

Page({
  data: {
    statusBarHeight: 44,
    // 用户身份 0=普通用户 1=护航
    userType: 0,
    // 用户信息
    isLogin: false,
    userInfo: {
      avatarUrl: '',
      nickName: '点击登录',
      userId: '',
      phone: ''
    },

    // ========== 普通用户版数据 ==========
    stats: {
      orderCount: 0,
      totalSpent: '0.00',
      completedCount: 0
    },
    orderTypes: [
      { id: 7, icon: '💳', text: '待支付' },
      { id: 0, icon: '⏳', text: '待接单' },
      { id: 1, icon: '🎮', text: '进行中' },
      { id: 5, icon: '🎯', text: '服务中' },
      { id: 6, icon: '📷', text: '待确认' },
      { id: 2, icon: '✅', text: '已完成' }
    ],
    menuList: [
      { id: 'wallet', icon: '💰', text: '我的钱包', desc: '余额与交易记录' },
      { id: 'favorites', icon: '⭐', text: '我的收藏', desc: '0 个收藏' },
      { id: 'invite', icon: '🎁', text: '邀请好友', desc: '邀请得奖励' }
    ],
    settingList: [
      { id: 'feedback', icon: '📝', text: '意见反馈' },
      { id: 'about', icon: 'ℹ️', text: '关于我们' },
      { id: 'setting', icon: '⚙️', text: '设置' }
    ],

    // ========== 护航版数据 ==========
    escortInfo: {
      level: '白银',
      region: '暗区突围合区'
    },
    escortWallet: {
      available: '0.00',
      totalEarn: '0.00',
      totalWithdraw: '0.00'
    },
    escortStats: {
      pending: 0,
      inService: 0,
      todayCompleted: 0,
      todayJoined: 0
    },

    // ========== 收益详情视图 ==========
    showEarningsDetail: false,
    earningsTab: 0, // 0=接单情况 1=结算记录 2=余额流水
    earningsData: {
      todayEarn: '0.00',
      yesterdayEarn: '0.00',
      monthEarn: '0.00',
      totalEarn: '0.00',
      todayCount: 0,
      yesterdayCount: 0,
      monthCount: 0,
      totalCount: 0
    },
    earningsOrderList: [],
    settlementList: [],
    flowList: [],
    searchKeyword: '',

    // 登录弹窗
    showLoginModal: false,
    loginAvatar: '',
    loginNickname: '',

    // 接单公告未读数
    announcementUnread: 0
  },

  onLoad() {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({ statusBarHeight: systemInfo.statusBarHeight })
    this.checkLoginStatus()
  },

  onShow() {
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 4 })
    }
    this.checkLoginStatus()
  },

  // 检查登录状态
  checkLoginStatus() {
    // 强制刷新用户信息，确保角色等数据是最新的
    userApi.getCurrentUser(true).then(userInfo => {
      if (userInfo && userInfo.nickName) {
        const userType = userInfo.userType || 0
        this.setData({
          isLogin: true,
          userInfo: userInfo,
          userType: userType
        })
        if (userType === 1) {
          this.loadEscortData()
        } else {
          this.loadUserData()
        }
      }
    })
  },

  // ========== 普通用户 ==========
  loadUserData() {
    const userInfo = this.data.userInfo
    Promise.all([
      favoriteApi.getFavorites(),
      userInfo.userId ? orderApi.getUserOrders(userInfo.userId, { pageSize: 1000 }) : Promise.resolve({ list: [], total: 0 })
    ]).then(([favorites, ordersData]) => {
      const orders = ordersData.list || ordersData || []
      const completed = orders.filter(o => o.status === 2).length
      const totalSpent = orders.reduce((sum, o) => sum + parseFloat(o.totalPrice || 0), 0)

      this.setData({
        stats: {
          orderCount: orders.length,
          totalSpent: totalSpent.toFixed(2),
          completedCount: completed
        },
        'menuList[1].desc': `${favorites.length} 个收藏`
      })
    })
  },

  onLoginTap() {
    if (this.data.isLogin) {
      wx.showToast({ title: '个人资料（开发中）', icon: 'none' })
      return
    }
    // 打开登录弹窗（使用头像昵称填写能力）
    this.setData({
      showLoginModal: true,
      loginAvatar: '',
      loginNickname: ''
    })
  },

  // 选择头像
  onChooseAvatar(e) {
    this.setData({ loginAvatar: e.detail.avatarUrl })
  },

  // 昵称输入
  onNicknameInput(e) {
    this.setData({ loginNickname: e.detail.value })
  },

  // 关闭登录弹窗
  closeLoginModal() {
    this.setData({ showLoginModal: false })
  },

  // 阻止事件冒泡
  stopPropagation() {},

  // 确认登录
  confirmLogin() {
    const { loginAvatar, loginNickname } = this.data
    if (!loginNickname.trim()) {
      wx.showToast({ title: '请输入昵称', icon: 'none' })
      return
    }
    wx.showLoading({ title: '登录中...' })
    // 使用 wx.login 获取 code
    wx.login({
      success: (loginRes) => {
        const code = loginRes.code || ''
        const userInfo = {
          avatarUrl: loginAvatar,
          nickName: loginNickname.trim()
        }
        // 调用登录接口
        userApi.login(code, userInfo).then(res => {
          wx.hideLoading()
          if (res && res.userInfo) {
            this.setData({
              isLogin: true,
              userInfo: res.userInfo,
              userType: res.userInfo.userType || 0,
              showLoginModal: false
            })
            if ((res.userInfo.userType || 0) === 1) {
              this.loadEscortData()
            } else {
              this.loadUserData()
            }
            wx.showToast({ title: '登录成功', icon: 'success' })
          } else {
            wx.showToast({ title: '登录失败', icon: 'none' })
          }
        }).catch(() => {
          wx.hideLoading()
          wx.showToast({ title: '登录失败', icon: 'none' })
        })
      },
      fail: () => {
        wx.hideLoading()
        wx.showToast({ title: '登录失败', icon: 'none' })
      }
    })
  },

  onLogout() {
    wx.showModal({
      title: '提示',
      content: '确定要退出登录吗？',
      success: (res) => {
        if (res.confirm) {
          userApi.logout().then(() => {
            this.setData({
              isLogin: false,
              userType: 0,
              showEarningsDetail: false,
              userInfo: {
                avatarUrl: '',
                nickName: '点击登录',
                userId: '',
                phone: ''
              },
              stats: {
                orderCount: 0,
                totalSpent: '0.00',
                completedCount: 0
              },
              'menuList[1].desc': '0 个收藏',
              escortInfo: {
                level: '白银',
                region: '暗区突围合区'
              },
              escortWallet: {
                available: '0.00',
                totalEarn: '0.00',
                totalWithdraw: '0.00'
              },
              escortStats: {
                pending: 0,
                inService: 0,
                todayCompleted: 0,
                todayJoined: 0
              },
              earningsData: {
                todayEarn: '0.00',
                yesterdayEarn: '0.00',
                monthEarn: '0.00',
                totalEarn: '0.00',
                todayCount: 0,
                yesterdayCount: 0,
                monthCount: 0,
                totalCount: 0
              },
              earningsOrderList: [],
              settlementList: [],
              flowList: [],
              searchKeyword: ''
            })
            wx.showToast({ title: '已退出登录', icon: 'none' })
          })
        }
      }
    })
  },

  onOrderTypeTap(e) {
    if (!this.data.isLogin) {
      wx.showToast({ title: '请先登录', icon: 'none' })
      return
    }
    const status = e.currentTarget.dataset.id
    // 状态码对应orders页面的tab索引
    const statusToTab = { 7: 1, 0: 2, 1: 3, 5: 4, 6: 5, 2: 6, 4: 7 }
    const tabIndex = statusToTab[status] || 0
    wx.navigateTo({
      url: `/pages/orders/orders?tab=${tabIndex}`
    })
  },

  onAllOrdersTap() {
    if (!this.data.isLogin) {
      wx.showToast({ title: '请先登录', icon: 'none' })
      return
    }
    wx.navigateTo({ url: '/pages/orders/orders' })
  },

  onMenuTap(e) {
    if (!this.data.isLogin) {
      wx.showToast({ title: '请先登录', icon: 'none' })
      return
    }
    const id = e.currentTarget.dataset.id
    const urls = {
      wallet: '/pages/wallet/wallet',
      favorites: '/pages/favorites/favorites',
      invite: '/pages/invite/invite'
    }
    if (urls[id]) {
      wx.navigateTo({ url: urls[id] })
    } else {
      wx.showToast({ title: '功能开发中', icon: 'none' })
    }
  },

  onSettingTap(e) {
    const id = e.currentTarget.dataset.id
    const urls = {
      feedback: '/pages/feedback/feedback',
      about: '/pages/about/about',
      setting: '/pages/setting/setting'
    }
    if (urls[id]) {
      wx.navigateTo({ url: urls[id] })
    }
  },

  // ========== 护航版 ==========
  loadEscortData() {
    const userId = this.data.userInfo.userId
    Promise.all([
      escortApi.getEscortWallet(userId),
      escortApi.getEscortStats(userId),
      applyApi.getUserApply(userId)
    ]).then(([wallet, stats, apply]) => {
      this.setData({
        escortWallet: {
          available: parseFloat(wallet.available).toFixed(2),
          totalEarn: parseFloat(wallet.totalEarn).toFixed(2),
          totalWithdraw: parseFloat(wallet.totalWithdraw).toFixed(2)
        },
        escortStats: stats,
        escortInfo: {
          level: this.data.userInfo.escortLevel || '白银',
          region: this.data.userInfo.gameRegion || (apply && apply.gameRegion) || '暗区突围合区'
        }
      })
    })

    // 加载公告未读数
    announcementApi.getLatest().then(res => {
      this.setData({ announcementUnread: (res && res.unreadCount) || 0 })
    }).catch(() => {})
  },

  // 打开收益详情
  openEarningsDetail() {
    const userId = this.data.userInfo.userId
    Promise.all([
      escortApi.getEarningsStats(userId),
      orderApi.getEscortOrders(userId, { pageSize: 1000 }),
      escortApi.getSettlementRecords(userId),
      escortApi.getBalanceFlow(userId)
    ]).then(([earningsData, ordersData, settlementsData, flowsData]) => {
      const orders = ordersData.list || ordersData || []
      // 加载订单列表（接单情况）
      const orderList = orders.slice().reverse().map(o => ({
        ...o,
        createTimeText: utils.formatTime(o.createTime),
        completeTimeText: o.completeTime ? utils.formatTime(o.completeTime) : ''
      }))

      // 加载结算记录
      const settlements = settlementsData.list || settlementsData || []
      const settlementList = settlements.map(s => ({
        ...s,
        timeText: utils.formatTime(s.time)
      }))

      // 加载余额流水
      const flows = flowsData.list || flowsData || []
      const flowList = flows.map(f => ({
        ...f,
        timeText: utils.formatTime(f.time)
      }))

      this.setData({
        showEarningsDetail: true,
        earningsTab: 0,
        earningsData: earningsData,
        earningsOrderList: orderList,
        settlementList: settlementList,
        flowList: flowList,
        searchKeyword: ''
      })
    })
  },

  // 关闭收益详情
  closeEarningsDetail() {
    this.setData({ showEarningsDetail: false })
  },

  // 切换收益tab
  switchEarningsTab(e) {
    const id = parseInt(e.currentTarget.dataset.id)
    this.setData({ earningsTab: id })
  },

  // 搜索输入
  onSearchInput(e) {
    this.setData({ searchKeyword: e.detail.value })
  },

  // 搜索订单
  onSearchOrder() {
    const keyword = this.data.searchKeyword.trim()
    const userId = this.data.userInfo.userId
    orderApi.getEscortOrders(userId, { pageSize: 1000 }).then(ordersData => {
      let orders = ordersData.list || ordersData || []
      if (keyword) {
        orders = orders.filter(o => o.orderId && o.orderId.indexOf(keyword) > -1)
      }

      const orderList = orders.slice().reverse().map(o => ({
        ...o,
        createTimeText: utils.formatTime(o.createTime),
        completeTimeText: o.completeTime ? utils.formatTime(o.completeTime) : ''
      }))

      this.setData({ earningsOrderList: orderList })
    })
  },

  // 复制文本
  onCopyText(e) {
    const text = e.currentTarget.dataset.text
    if (!text) return
    wx.setClipboardData({
      data: text,
      success: () => {
        wx.showToast({ title: '已复制', icon: 'success' })
      }
    })
  },

  // 查看回执单
  viewReceipt() {
    wx.showToast({ title: '回执单功能开发中', icon: 'none' })
  },

  // 联系客服
  onContactKefu() {
    wx.showToast({ title: '客服功能开发中', icon: 'none' })
  },

  // 提现
  onWithdraw() {
    wx.showToast({ title: '提现功能开发中', icon: 'none' })
  },

  // 接单公告
  onAnnouncement() {
    this.setData({ announcementUnread: 0 })
    wx.navigateTo({ url: '/pages/announcement/announcement' })
  },

  // 接单验证
  onVerify() {
    wx.showToast({ title: '验证功能开发中', icon: 'none' })
  },

  // 服务订单
  onServiceOrders() {
    wx.navigateTo({ url: '/pages/escortOrders/escortOrders' })
  },

  // 抢单大厅
  onGrabHall() {
    wx.navigateTo({ url: '/pages/grabHall/grabHall' })
  },

  // 我的消息
  onEscortMessage() {
    wx.showToast({ title: '消息功能开发中', icon: 'none' })
  },

  // 我的资料
  onEscortProfile() {
    wx.navigateTo({ url: '/pages/escortProfile/escortProfile' })
  },

  // 投诉记录
  onComplaint() {
    wx.showToast({ title: '投诉记录开发中', icon: 'none' })
  }
})
