// app.js
const { userApi } = require('./utils/api.js')
const { loadAllFromServer } = require('./utils/services.js')

App({
  globalData: {
    // 系统信息
    systemInfo: null,
    // 用户信息
    userInfo: null,
    isLogin: false,
    // 主题色
    themeColor: '#7B61FF',
    // 版本号
    version: '1.0.0'
  },

  onLaunch() {
    // 获取系统信息
    try {
      const systemInfo = wx.getSystemInfoSync()
      this.globalData.systemInfo = systemInfo
    } catch (e) {
      console.error('获取系统信息失败', e)
    }

    // 检查登录态
    this.checkLoginStatus()

    // 检查更新
    this.checkUpdate()

    // 从后端加载服务、分类、轮播图（失败则使用本地兜底数据）
    loadAllFromServer()
  },

  onShow() {
    // 每次显示时检查登录状态
    this.checkLoginStatus()
  },

  onError(msg) {
    // 全局错误处理
    console.error('小程序全局错误：', msg)
    // 可以在这里上报错误信息到服务器
  },

  onUnhandledRejection(res) {
    // 未处理的 Promise 拒绝
    console.error('未处理的 Promise 拒绝：', res.reason)
  },

  // 检查登录状态
  checkLoginStatus() {
    return new Promise((resolve) => {
      userApi.getCurrentUser().then(userInfo => {
        if (userInfo && userInfo.nickName) {
          this.globalData.userInfo = userInfo
          this.globalData.isLogin = true
        } else {
          this.globalData.userInfo = null
          this.globalData.isLogin = false
        }
        resolve(this.globalData.isLogin)
      }).catch(() => {
        this.globalData.userInfo = null
        this.globalData.isLogin = false
        resolve(false)
      })
    })
  },

  // 检查小程序更新
  checkUpdate() {
    if (typeof wx.getUpdateManager === 'function') {
      const updateManager = wx.getUpdateManager()

      updateManager.onCheckForUpdate((res) => {
        if (res.hasUpdate) {
          console.log('发现新版本')
        }
      })

      updateManager.onUpdateReady(() => {
        wx.showModal({
          title: '更新提示',
          content: '新版本已经准备好，是否重启应用？',
          success: (res) => {
            if (res.confirm) {
              updateManager.applyUpdate()
            }
          }
        })
      })

      updateManager.onUpdateFailed(() => {
        console.error('新版本下载失败')
      })
    }
  },

  // 获取用户信息（带登录检查）
  requireLogin() {
    return new Promise((resolve, reject) => {
      if (this.globalData.isLogin && this.globalData.userInfo) {
        resolve(this.globalData.userInfo)
      } else {
        wx.showToast({
          title: '请先登录',
          icon: 'none'
        })
        reject(new Error('未登录'))
      }
    })
  }
})
