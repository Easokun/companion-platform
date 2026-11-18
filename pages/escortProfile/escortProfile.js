// pages/escortProfile/escortProfile.js
const { escortApi, userApi, utils, APPLY_STATUS } = require('../../utils/api.js')

Page({
  data: {
    statusBarHeight: 44,
    profile: null,
    auditStatus: null,
    // 表单数据
    formData: {
      nickname: '',
      avatar: '',
      gender: '男',
      age: '',
      city: '',
      intro: '',
      // 游戏信息
      mainGame: '暗区突围',
      gameId: '',
      gameLevel: '',
      gameRegion: 'qv区',
      // 服务信息
      serviceTypes: [],
      availableTime: '',
      // 相册
      photoAlbum: []
    },
    photoMax: 5,
    // 游戏列表
    gameOptions: ['暗区突围', '王者荣耀', '和平精英', '英雄联盟', '原神'],
    // 服务类型
    serviceOptions: [
      { id: 'escort', name: '王牌护航', checked: false },
      { id: 'tech', name: '技术带飞', checked: false },
      { id: 'play', name: '欢乐陪玩', checked: false },
      { id: '代打', name: '专业陪玩', checked: false }
    ],
    // 时间段
    timeOptions: ['全天', '白天', '晚上', '深夜', '周末'],
    selectedTimeIndex: 0,
    hasShownReject: false // 是否已显示过拒绝弹窗，避免重复显示
  },

  onLoad() {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({ statusBarHeight: systemInfo.statusBarHeight })
    this.loadProfile()
  },

  _editing: false,

  onShow() {
    // 如果用户正在编辑表单（如上传照片返回），不重新加载，避免清空表单
    if (this._editing) {
      this._editing = false
      return
    }
    this.loadProfile()
  },

  // 显示拒绝原因弹窗
  showRejectModal(audit) {
    const reason = audit.auditReason || '您的资料不符合要求，请修改后重新提交'
    wx.showModal({
      title: '资料审核未通过',
      content: reason,
      confirmText: '我知道了',
      showCancel: false,
      confirmColor: '#7B61FF'
    })
  },

  loadProfile() {
    userApi.getCurrentUser().then(user => {
      if (!user || !user.userId) return

      // 获取当前资料（用自己的资料接口，返回完整字段，且已合并审核中待生效内容）
      escortApi.getMyProfile().then(profile => {
        // 获取最新审核状态
        escortApi.getLatestProfileAudit(user.userId).then(latestAudit => {
          let formData = { ...this.data.formData }
          let serviceOptions = this.data.serviceOptions
          let selectedTimeIndex = 0

          if (profile) {
            // 填充表单 —— 兼容旧数据：如果 serviceTypes 存的是 name（旧格式），自动转成 id
            const rawTypes = profile.serviceTypes || []
            const optMap = {}
            this.data.serviceOptions.forEach(s => { optMap[s.id] = s; optMap[s.name] = s })
            // 归一化为 id 数组
            const serviceTypeIds = rawTypes.map(t => {
              if (optMap[t]) return optMap[t].id
              // 如果找不到，尝试模糊匹配 name
              const found = this.data.serviceOptions.find(s => s.name === t)
              return found ? found.id : t
            }).filter(Boolean)

            serviceOptions = this.data.serviceOptions.map(s => ({
              ...s,
              checked: serviceTypeIds.indexOf(s.id) > -1
            }))
            const timeIndex = this.data.timeOptions.indexOf(profile.availableTime || '全天')
            selectedTimeIndex = timeIndex > -1 ? timeIndex : 0

            formData = {
              ...formData,
              nickname: profile.nickname || '',
              avatar: profile.avatar || '',
              gender: profile.gender || '男',
              age: profile.age || '',
              city: profile.city || '',
              intro: profile.intro || '',
              mainGame: profile.mainGame || '暗区突围',
              gameId: profile.gameId || '',
              gameLevel: profile.gameLevel || '',
              gameRegion: profile.gameRegion || 'qv区',
              photoAlbum: profile.photoAlbum || [],
              serviceTypes: serviceTypeIds,
              availableTime: profile.availableTime || '全天'
            }
          }

          // 如果有待审核的记录，将审核中的新值合并到表单显示（让用户看到自己刚提交的内容）
          if (latestAudit && latestAudit.status === 0 && latestAudit.field === 'profile_all' && latestAudit.newValue) {
            try {
              const pendingChanges = typeof latestAudit.newValue === 'string'
                ? JSON.parse(latestAudit.newValue)
                : latestAudit.newValue

              // 字段映射：数据库字段名 -> formData 字段名
              const fieldMap = {
                nickname: 'nickname',
                avatar: 'avatar',
                bio: 'intro',
                phone: 'phone',
                game: 'mainGame',
                level: 'gameLevel',
                gender: 'gender',
                age: 'age',
                city: 'city',
                photo_album: 'photoAlbum',
                game_id: 'gameId',
                game_region: 'gameRegion',
                service_types: 'serviceTypes',
                available_time: 'availableTime'
              }

              Object.keys(pendingChanges).forEach(dbField => {
                const formField = fieldMap[dbField]
                if (!formField) return
                let val = pendingChanges[dbField]
                if (val === null || val === undefined || val === 'None' || val === '') return

                // 数组字段需要 JSON 解析（photo_album、service_types）
                if (dbField === 'photo_album' || dbField === 'service_types') {
                  try {
                    if (typeof val === 'string') val = JSON.parse(val)
                  } catch (e) {
                    // 解析失败就跳过
                    return
                  }
                }

                formData[formField] = val
              })

              // 重新计算 serviceOptions 的选中状态
              if (formData.serviceTypes && Array.isArray(formData.serviceTypes)) {
                const optMap2 = {}
                this.data.serviceOptions.forEach(s => { optMap2[s.id] = s; optMap2[s.name] = s })
                const typeIds = formData.serviceTypes.map(t => {
                  if (optMap2[t]) return optMap2[t].id
                  const found = this.data.serviceOptions.find(s => s.name === t)
                  return found ? found.id : t
                }).filter(Boolean)
                serviceOptions = this.data.serviceOptions.map(s => ({
                  ...s,
                  checked: typeIds.indexOf(s.id) > -1
                }))
              }

              // 重新计算时间段索引
              if (formData.availableTime) {
                const tIdx = this.data.timeOptions.indexOf(formData.availableTime)
                selectedTimeIndex = tIdx > -1 ? tIdx : 0
              }
            } catch (e) {
              // 解析失败就用主表数据
            }
          }

          this.setData({
            formData,
            serviceOptions,
            selectedTimeIndex,
            profile,
            auditStatus: latestAudit
          })

          // 如果最新审核是拒绝状态，显示拒绝原因弹窗（仅在本次进入页面时显示一次）
          if (latestAudit && latestAudit.status === 2 && !this.data.hasShownReject) {
            this.setData({ hasShownReject: true })
            setTimeout(() => {
              this.showRejectModal(latestAudit)
            }, 300)
          }
        })
      })
    })
  },

  // 输入处理
  onInput(e) {
    const field = e.currentTarget.dataset.field
    this.setData({
      [`formData.${field}`]: e.detail.value
    })
  },

  // 性别选择
  onGenderChange(e) {
    this.setData({ 'formData.gender': e.detail.value })
  },

  // 游戏选择
  onGameChange(e) {
    const idx = e.detail.value
    this.setData({ 'formData.mainGame': this.data.gameOptions[idx] })
  },

  // 服务类型选择
  onServiceToggle(e) {
    const id = e.currentTarget.dataset.id
    const serviceOptions = this.data.serviceOptions.map(s => {
      if (s.id === id) {
        return { ...s, checked: !s.checked }
      }
      return s
    })
    this.setData({ serviceOptions })
  },

  // 时间段选择
  onTimeChange(e) {
    const idx = e.detail.value
    this.setData({
      selectedTimeIndex: idx,
      'formData.availableTime': this.data.timeOptions[idx]
    })
  },

  // 选择头像
  chooseAvatar() {
    this._editing = true
    wx.chooseImage({
      count: 1,
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: async (res) => {
        try {
          // 将临时路径保存为持久化路径，避免过期失效
          const savedPath = await utils.saveImageToLocal(res.tempFilePaths[0])
          this.setData({ 'formData.avatar': savedPath })
        } catch (err) {
          // 保存失败时退回使用临时路径
          this.setData({ 'formData.avatar': res.tempFilePaths[0] })
        }
      }
    })
  },

  // 选择相册照片
  chooseAlbumPhoto() {
    this._editing = true
    const remain = this.data.photoMax - this.data.formData.photoAlbum.length
    if (remain <= 0) {
      wx.showToast({ title: `最多${this.data.photoMax}张照片`, icon: 'none' })
      return
    }
    wx.chooseImage({
      count: remain,
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: async (res) => {
        const tempPaths = res.tempFilePaths.slice(0, remain)
        try {
          // 批量保存为持久化路径
          const savedPaths = await utils.saveImagesToLocal(tempPaths)
          const photoAlbum = [...this.data.formData.photoAlbum, ...savedPaths]
          this.setData({ 'formData.photoAlbum': photoAlbum })
        } catch (err) {
          // 保存失败时退回使用临时路径
          const photoAlbum = [...this.data.formData.photoAlbum, ...tempPaths]
          this.setData({ 'formData.photoAlbum': photoAlbum })
        }
      }
    })
  },

  // 删除相册照片
  deleteAlbumPhoto(e) {
    const index = e.currentTarget.dataset.index
    const photoAlbum = this.data.formData.photoAlbum.filter((_, i) => i !== index)
    this.setData({ 'formData.photoAlbum': photoAlbum })
  },

  // 预览照片
  previewPhoto(e) {
    const current = e.currentTarget.dataset.url
    const photos = this.data.formData.photoAlbum
    wx.previewImage({ current, urls: photos })
  },

  // 提交审核
  submitAudit() {
    const formData = this.data.formData

    if (!formData.nickname.trim()) {
      wx.showToast({ title: '请输入护航昵称', icon: 'none' })
      return
    }
    if (!formData.gameId.trim()) {
      wx.showToast({ title: '请输入游戏ID', icon: 'none' })
      return
    }
    if (!formData.gameLevel.trim()) {
      wx.showToast({ title: '请输入游戏段位', icon: 'none' })
      return
    }

    const serviceTypeIds = this.data.serviceOptions.filter(s => s.checked).map(s => s.id)
    if (serviceTypeIds.length === 0) {
      wx.showToast({ title: '请选择服务类型', icon: 'none' })
      return
    }

    userApi.getCurrentUser().then(user => {
      if (!user || !user.userId) return

      // 检查是否已有待审核记录
      escortApi.getLatestProfileAudit(user.userId).then(latestAudit => {
        if (latestAudit && latestAudit.status === APPLY_STATUS.PENDING) {
          wx.showToast({ title: '资料审核中，请耐心等待，不要重复提交', icon: 'none' })
          return
        }

        wx.showModal({
          title: '提交审核',
          content: '确认提交资料修改审核吗？审核通过后资料将更新。',
          success: (res) => {
            if (res.confirm) {
              this._doSubmitAudit(user.userId, formData, serviceTypeIds)
            }
          }
        })
      })
    })
  },

  // 内部：执行提交审核（先上传图片再提交）
  _doSubmitAudit(userId, formData, serviceTypeIds) {
    wx.showLoading({ title: '上传图片中...' })

    const uploadTasks = []
    let finalAvatar = formData.avatar
    let finalPhotoAlbum = formData.photoAlbum

    // 上传头像（如果是本地路径且不是http开头的远程路径）
    if (formData.avatar && !formData.avatar.startsWith('http')) {
      uploadTasks.push(
        utils.uploadFile(formData.avatar, 'avatar').then(url => {
          finalAvatar = url
        })
      )
    }

    // 上传相册照片（过滤出本地路径）
    // 筛选需要上传的本地图片（微信临时路径 http://tmp/ 和 wxfile:// 都算本地，需要上传到服务器）
    const localPhotos = (formData.photoAlbum || []).filter(p => {
      if (!p) return false
      // 已经是服务器域名的图片才不用重新上传
      return !p.includes('uploads/') && !p.startsWith('https://') && !p.startsWith('http://') && !p.startsWith('http://tmp/');
    })
    // 同时处理 http://tmp/ 开头的微信临时文件
    const tmpPhotos = (formData.photoAlbum || []).filter(p => p && p.startsWith('http://tmp/'))
    const allLocalPhotos = [...localPhotos, ...tmpPhotos]
    if (allLocalPhotos.length > 0) {
      uploadTasks.push(
        utils.uploadFiles(allLocalPhotos, 'profile').then(uploadedUrls => {
          // 替换本地路径为服务器URL，保留已经是远程URL的图片
          const urlMap = {}
          allLocalPhotos.forEach((localPath, idx) => {
            urlMap[localPath] = uploadedUrls[idx]
          })
          finalPhotoAlbum = (formData.photoAlbum || []).map(p => urlMap[p] || p)
        })
      )
    }

    Promise.all(uploadTasks).then(() => {
      wx.hideLoading()
      wx.showLoading({ title: '提交中...' })

      const submitData = {
        ...formData,
        avatar: finalAvatar,
        photoAlbum: finalPhotoAlbum,
        serviceTypes: serviceTypeIds,
        availableTime: this.data.timeOptions[this.data.selectedTimeIndex]
      }

      escortApi.submitProfileAudit(userId, submitData).then(() => {
        wx.hideLoading()
        wx.showToast({ title: '已提交审核', icon: 'success' })
        setTimeout(() => {
          wx.navigateBack()
        }, 1500)
      }).catch(err => {
        wx.hideLoading()
        wx.showToast({ title: err.msg || '提交失败', icon: 'none' })
      })
    }).catch(err => {
      wx.hideLoading()
      wx.showToast({ title: '图片上传失败，请重试', icon: 'none' })
    })
  },

  goBack() {
    wx.navigateBack()
  }
})
