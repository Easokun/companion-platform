// pages/joinApply/joinApply.js
const { applyApi, userApi, utils } = require('../../utils/api.js')

Page({
  data: {
    statusBarHeight: 44,
    // 基础信息
    realName: '',
    gender: '',
    city: '',
    // 联系方式
    qq: '',
    wechat: '',
    phone: '',
    email: '',
    // 上传照片
    photos: [],
    photoMax: 4,
    // 游戏段位
    gameLevel: '',
    // 是否参加考核
    joinExam: '',
    // 城市选择
    cityColumns: ['北京', '上海', '广州', '深圳', '杭州', '成都', '武汉', '南京', '重庆', '西安', '苏州', '天津', '长沙', '郑州', '东莞', '青岛', '沈阳', '合肥', '福州', '昆明', '其他']
  },

  onLoad() {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({ statusBarHeight: systemInfo.statusBarHeight })

    // 检查封禁状态
    userApi.getCurrentUser().then(user => {
      if (user && user.userId) {
        applyApi.checkBanStatus(user.userId).then(banInfo => {
          if (banInfo.banned) {
            wx.showModal({
              title: '无法申请',
              content: banInfo.reason + '，解封时间：' + banInfo.banEndTime,
              showCancel: false,
              success: () => {
                wx.navigateBack()
              }
            })
          }
        })
      }
    })
  },

  goBack() {
    wx.navigateBack()
  },

  // 输入姓名
  onNameInput(e) {
    this.setData({ realName: e.detail.value })
  },

  // 选择性别
  onGenderChange(e) {
    this.setData({ gender: e.detail.value })
  },

  // 选择城市
  onCityChange(e) {
    const idx = e.detail.value
    this.setData({ city: this.data.cityColumns[idx] })
  },

  // QQ
  onQqInput(e) {
    this.setData({ qq: e.detail.value })
  },

  // 微信
  onWechatInput(e) {
    this.setData({ wechat: e.detail.value })
  },

  // 手机号
  onPhoneInput(e) {
    this.setData({ phone: e.detail.value })
  },

  // 邮箱
  onEmailInput(e) {
    this.setData({ email: e.detail.value })
  },

  // 游戏段位
  onGameLevelInput(e) {
    this.setData({ gameLevel: e.detail.value })
  },

  // 上传照片
  choosePhoto() {
    if (this.data.photos.length >= this.data.photoMax) {
      wx.showToast({ title: '最多上传4张', icon: 'none' })
      return
    }
    wx.chooseImage({
      count: this.data.photoMax - this.data.photos.length,
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        const tempPaths = res.tempFilePaths
        // 直接使用临时路径（wx.uploadFile 对临时路径支持最好）
        this.setData({
          photos: [...this.data.photos, ...tempPaths].slice(0, this.data.photoMax)
        })
      },
      fail: (err) => {
        console.error('选择图片失败', err)
        wx.showToast({ title: '选择图片失败', icon: 'none' })
      }
    })
  },

  // 预览照片
  previewPhoto(e) {
    const idx = e.currentTarget.dataset.index
    const urls = this.data.photos
    wx.previewImage({
      current: urls[idx],
      urls: urls
    })
  },

  // 删除照片
  deletePhoto(e) {
    const idx = e.currentTarget.dataset.index
    const photos = this.data.photos
    photos.splice(idx, 1)
    this.setData({ photos })
  },

  // 选择是否参加考核
  onExamChange(e) {
    this.setData({ joinExam: e.detail.value })
  },

  // 提交申请
  submitApply() {
    const { realName, gender, city, phone, photos, joinExam } = this.data

    // 验证
    if (!realName.trim()) {
      wx.showToast({ title: '请输入真实姓名', icon: 'none' })
      return
    }
    if (!gender) {
      wx.showToast({ title: '请选择性别', icon: 'none' })
      return
    }
    if (!city) {
      wx.showToast({ title: '请选择所在城市', icon: 'none' })
      return
    }
    if (!phone.trim()) {
      wx.showToast({ title: '请输入手机号', icon: 'none' })
      return
    }
    if (!/^1[3-9]\d{9}$/.test(phone)) {
      wx.showToast({ title: '手机号格式不正确', icon: 'none' })
      return
    }
    if (photos.length === 0) {
      wx.showToast({ title: '请上传游戏水平截图', icon: 'none' })
      return
    }
    if (!this.data.gameLevel.trim()) {
      wx.showToast({ title: '请输入游戏段位', icon: 'none' })
      return
    }
    if (!joinExam) {
      wx.showToast({ title: '请选择是否参加考核', icon: 'none' })
      return
    }

    userApi.getCurrentUser().then(user => {
      if (!user || !user.userId) {
        wx.showToast({ title: '请先登录', icon: 'none' })
        return
      }

      // 再次检查封禁
      applyApi.checkBanStatus(user.userId).then(banInfo => {
        if (banInfo.banned) {
          wx.showModal({
            title: '无法申请',
            content: banInfo.reason + '，解封时间：' + banInfo.banEndTime,
            showCancel: false
          })
          return
        }

        wx.showLoading({ title: '上传图片中...' })
        // 先上传照片到服务器
        utils.uploadFiles(photos, 'apply').then(uploadedUrls => {
          wx.hideLoading()
          // 保存申请数据
          const applyData = {
            userId: user.userId,
            nickName: user.nickName,
            realName: realName.trim(),
            gender: gender,
            city: city,
            qq: this.data.qq.trim(),
            wechat: this.data.wechat.trim(),
            phone: phone.trim(),
            email: this.data.email.trim(),
            photos: uploadedUrls,
            takeExam: joinExam === '是',
            gameLevel: this.data.gameLevel.trim(),
            gameRegion: '暗区突围合区'
          }

          wx.showLoading({ title: '提交中...' })
          applyApi.submitApply(applyData).then(() => {
            wx.hideLoading()
            wx.showModal({
              title: '提交成功',
              content: '您的申请将在1-3个工作日内审核，请耐心等待',
              showCancel: false,
              confirmText: '知道了',
              success: () => {
                wx.navigateBack()
              }
            })
          }).catch(err => {
            wx.hideLoading()
            wx.showToast({ title: err.msg || '提交失败', icon: 'none' })
          })
        }).catch(err => {
          wx.hideLoading()
          wx.showToast({ title: '图片上传失败，请重试', icon: 'none' })
        })
      })
    })
  }
})
