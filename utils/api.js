// utils/api.js
// 数据层统一封装 —— 支持后端接口模式和本地存储模式
// 设置 USE_REMOTE = true 走后端接口，= false 走本地存储（调试用）

// ==================== 环境配置 ====================

// TODO: 改成你的后端接口地址
const BASE_URL = 'https://api.luhuodianjing.com/api'

// 是否使用远程后端接口（false 时使用本地存储，方便本地调试）
const USE_REMOTE = true

// ==================== 常量定义 ====================

// 订单状态常量
const ORDER_STATUS = {
  PENDING: 0,      // 待接单
  IN_PROGRESS: 1,  // 进行中（已接单）
  COMPLETED: 2,    // 已完成
  CANCELLED: 4,    // 已取消
  IN_SERVICE: 5,   // 服务中
  TO_CONFIRM: 6,   // 待确认
  PENDING_PAYMENT: 7  // 待支付
}

// 订单状态流转规则（当前状态 → 允许的下一状态）
const ORDER_STATUS_FLOW = {
  [ORDER_STATUS.PENDING_PAYMENT]: [ORDER_STATUS.PENDING, ORDER_STATUS.CANCELLED],
  [ORDER_STATUS.PENDING]: [ORDER_STATUS.IN_PROGRESS, ORDER_STATUS.CANCELLED],
  [ORDER_STATUS.IN_PROGRESS]: [ORDER_STATUS.IN_SERVICE, ORDER_STATUS.PENDING],
  [ORDER_STATUS.IN_SERVICE]: [ORDER_STATUS.TO_CONFIRM],
  [ORDER_STATUS.TO_CONFIRM]: [ORDER_STATUS.COMPLETED, ORDER_STATUS.IN_SERVICE],
  [ORDER_STATUS.COMPLETED]: [],
  [ORDER_STATUS.CANCELLED]: []
}

// 申请状态常量
const APPLY_STATUS = {
  PENDING: 0,     // 审核中
  APPROVED: 1,    // 已通过
  REJECTED: 2,    // 已拒绝
  CANCELLED: 3,   // 已取消
  REVOKED: 4      // 已撤销
}

// 用户类型
const USER_TYPE = {
  NORMAL: 0,    // 普通用户
  ESCORT: 1     // 护航打手
}

// 平台抽成比例（护航拿70%）
const PLATFORM_COMMISSION = 0.7

// 抢单配置
const GRAB_CONFIG = {
  MAX_ACTIVE_ORDERS: 5  // 同时进行中的最大订单数
}

// ==================== 网络请求封装 ====================

// 从本地存储获取 token
function getToken() {
  return wx.getStorageSync('token') || ''
}

// 保存 token
function setToken(token) {
  wx.setStorageSync('token', token)
}

// 中文状态 → 数字状态映射
const STATUS_TEXT_TO_NUM = {
  '待接单': ORDER_STATUS.PENDING,
  '进行中': ORDER_STATUS.IN_PROGRESS,
  '已完成': ORDER_STATUS.COMPLETED,
  '已取消': ORDER_STATUS.CANCELLED,
  '服务中': ORDER_STATUS.IN_SERVICE,
  '待确认': ORDER_STATUS.TO_CONFIRM,
  '待支付': ORDER_STATUS.PENDING_PAYMENT
}

// 数字状态 → 中文状态映射
const STATUS_NUM_TO_TEXT = {
  [ORDER_STATUS.PENDING]: '待接单',
  [ORDER_STATUS.IN_PROGRESS]: '进行中',
  [ORDER_STATUS.COMPLETED]: '已完成',
  [ORDER_STATUS.CANCELLED]: '已取消',
  [ORDER_STATUS.IN_SERVICE]: '服务中',
  [ORDER_STATUS.TO_CONFIRM]: '待确认',
  [ORDER_STATUS.PENDING_PAYMENT]: '待支付'
}

// 转换订单状态（中文→数字），仅处理明确是订单的数据（有 orderId 字段），避免误转换申请等其他数据的 status
function convertStatusInData(data) {
  if (!data || typeof data !== 'object') return data
  if (Array.isArray(data)) {
    return data.map(item => convertStatusInData(item))
  }
  // 只有包含 orderId 字段的数据才认为是订单，才转换状态
  // 避免误转换申请（apply）的 status（申请的 0 是待审核，订单的 0 是待接单）
  if (data.orderId === undefined && data.id === undefined) {
    return data
  }
  // 再检查一下：如果有 serviceName 或 serviceType 等订单特有字段，才转换
  const isOrderData = data.orderId !== undefined || data.serviceName !== undefined || data.serviceType !== undefined || data.totalPrice !== undefined
  if (!isOrderData) {
    return data
  }
  // 处理当前对象的 status 字段
  if (data.status !== undefined && data.status !== null) {
    // 如果 status 是中文文本，转换为数字
    if (STATUS_TEXT_TO_NUM[data.status] !== undefined) {
      const numStatus = STATUS_TEXT_TO_NUM[data.status]
      data.status = numStatus
      data.statusText = STATUS_NUM_TO_TEXT[numStatus]
    }
    // 如果 status 是数字，确保有 statusText
    else if (typeof data.status === 'number' && STATUS_NUM_TO_TEXT[data.status] !== undefined) {
      data.statusText = STATUS_NUM_TO_TEXT[data.status]
    }
  }
  // 仅对已知的订单子对象字段递归（escortProfile、order 等），不盲目递归所有子对象
  const orderSubKeys = ['escortProfile', 'order', 'orderInfo']
  for (const key of orderSubKeys) {
    if (data[key] && typeof data[key] === 'object') {
      data[key] = convertStatusInData(data[key])
    }
  }
  return data
}

// 本地列表分页工具
function paginateList(list, page = 1, pageSize = 10) {
  const total = list.length
  const p = Math.max(1, parseInt(page) || 1)
  const ps = Math.max(1, parseInt(pageSize) || 10)
  const start = (p - 1) * ps
  const end = start + ps
  return {
    list: list.slice(start, end),
    total,
    page: p,
    pageSize: ps
  }
}

// 统一请求方法
function request(options) {
  return new Promise((resolve, reject) => {
    const { url, method = 'GET', data = {}, header = {} } = options

    wx.request({
      url: BASE_URL + url,
      method,
      data,
      header: {
        'content-type': 'application/json',
        'Authorization': getToken() ? 'Bearer ' + getToken() : '',
        ...header
      },
      success: (res) => {
        if (res.statusCode === 200) {
          if (res.data && res.data.code === 0) {
            // 统一转换订单状态（中文→数字）
            const converted = convertStatusInData(res.data.data)
            resolve(converted)
          } else if (res.data && res.data.code === 401) {
            // token 过期，清除本地登录态
            wx.removeStorageSync('token')
            wx.removeStorageSync('userInfo')
            wx.showToast({ title: '登录已过期，请重新登录', icon: 'none' })
            reject(res.data)
          } else {
            wx.showToast({ title: res.data?.msg || '请求失败', icon: 'none' })
            reject(res.data)
          }
        } else {
          wx.showToast({ title: '网络错误 ' + res.statusCode, icon: 'none' })
          reject(res)
        }
      },
      fail: (err) => {
        wx.showToast({ title: '网络连接失败', icon: 'none' })
        reject(err)
      }
    })
  })
}

// ==================== 工具函数 ====================
const utils = {
  // 生成当前时间戳
  now() {
    return Date.now()
  },

  // 格式化时间为 24小时制 YYYY-MM-DD HH:mm:ss
  // 兼容后端返回的字符串格式 '2025-01-01 12:00:00' 和数字时间戳
  formatTime(timestamp) {
    if (!timestamp) return ''
    // 后端返回的已经是格式化字符串，直接返回
    if (typeof timestamp === 'string' && /^\d{4}-\d{2}-\d{2}/.test(timestamp)) {
      return timestamp
    }
    const date = new Date(Number(timestamp))
    if (isNaN(date.getTime())) return ''
    const y = date.getFullYear()
    const m = String(date.getMonth() + 1).padStart(2, '0')
    const d = String(date.getDate()).padStart(2, '0')
    const h = String(date.getHours()).padStart(2, '0')
    const min = String(date.getMinutes()).padStart(2, '0')
    const s = String(date.getSeconds()).padStart(2, '0')
    return `${y}-${m}-${d} ${h}:${min}:${s}`
  },

  // 格式化日期 YYYY-MM-DD
  formatDate(timestamp) {
    if (!timestamp) return ''
    if (typeof timestamp === 'string' && /^\d{4}-\d{2}-\d{2}/.test(timestamp)) {
      return timestamp.substring(0, 10)
    }
    const date = new Date(Number(timestamp))
    if (isNaN(date.getTime())) return ''
    const y = date.getFullYear()
    const m = String(date.getMonth() + 1).padStart(2, '0')
    const d = String(date.getDate()).padStart(2, '0')
    return `${y}-${m}-${d}`
  },

  // 获取某天的开始时间戳（0点0分）
  getDayStart(timestamp) {
    const date = new Date(Number(timestamp))
    date.setHours(0, 0, 0, 0)
    return date.getTime()
  },

  // 判断是否是今天
  isToday(timestamp) {
    if (!timestamp) return false
    return this.getDayStart(timestamp) === this.getDayStart(Date.now())
  },

  // ==================== 金额工具（分单位计算） ====================
  // 元转分
  yuanToFen(yuan) {
    return Math.round(parseFloat(yuan || 0) * 100)
  },

  // 分转元（保留2位小数的字符串）
  fenToYuan(fen) {
    return (parseInt(fen || 0) / 100).toFixed(2)
  },

  // 分转元（数字类型）
  fenToYuanNum(fen) {
    return parseInt(fen || 0) / 100
  },

  // 格式化金额显示（分转元，带两位小数）
  formatMoney(fen) {
    return (parseInt(fen || 0) / 100).toFixed(2)
  },

  // 生成唯一ID（前缀+时间戳+随机数）
  generateId(prefix = 'ID') {
    const now = Date.now()
    const rand = Math.floor(Math.random() * 10000).toString().padStart(4, '0')
    return prefix + now + rand
  },

  // ==================== 图片持久化工具 ====================
  // 将临时路径图片保存到本地文件系统，返回持久化路径
  saveImageToLocal(tempFilePath) {
    return new Promise((resolve, reject) => {
      if (!tempFilePath) {
        reject(new Error('图片路径为空'))
        return
      }
      if (tempFilePath.startsWith('wxfile://') || tempFilePath.startsWith('http')) {
        resolve(tempFilePath)
        return
      }
      const fs = wx.getFileSystemManager()
      const ext = tempFilePath.split('.').pop() || 'jpg'
      const savePath = `${wx.env.USER_DATA_PATH}/img_${Date.now()}_${Math.floor(Math.random() * 10000)}.${ext}`
      fs.saveFile({
        tempFilePath: tempFilePath,
        filePath: savePath,
        success: (res) => resolve(res.savedFilePath),
        fail: (err) => reject(err)
      })
    })
  },

  // 批量保存图片到本地
  saveImagesToLocal(tempFilePaths) {
    const promises = tempFilePaths.map(p => this.saveImageToLocal(p))
    return Promise.all(promises)
  },

  // 删除本地保存的图片
  removeLocalImage(filePath) {
    return new Promise((resolve) => {
      if (!filePath || !filePath.startsWith('wxfile://')) {
        resolve(true)
        return
      }
      const fs = wx.getFileSystemManager()
      fs.unlink({
        filePath: filePath,
        success: () => resolve(true),
        fail: () => resolve(false)
      })
    })
  },

  // ==================== 文件上传 ====================
  // 上传文件到后端服务器，返回服务器URL
  // 压缩图片（质量80，大图自动压缩，小图跳过）
  compressImage(filePath) {
    return new Promise((resolve) => {
      // 只压缩 jpg/jpeg/png，gif 和 webp 跳过
      const lower = filePath.toLowerCase()
      if (lower.includes('.gif') || lower.includes('.webp')) {
        resolve(filePath)
        return
      }
      wx.compressImage({
        src: filePath,
        quality: 80,
        success: (res) => {
          console.log('[上传] 图片压缩成功:', {
            原路径: filePath,
            压缩后: res.tempFilePath
          })
          resolve(res.tempFilePath)
        },
        fail: (err) => {
          console.warn('[上传] 图片压缩失败，使用原图:', err)
          resolve(filePath) // 压缩失败就用原图，不阻断上传
        }
      })
    })
  },

  // 上传单个文件（先压缩再上传）
  uploadFile(filePath, bizType = 'general') {
    if (!USE_REMOTE) {
      // 本地模式直接返回原路径
      return Promise.resolve(filePath)
    }
    // 先压缩图片再上传
    return this.compressImage(filePath).then(compressedPath => {
      return new Promise((resolve, reject) => {
        const token = getToken()
        const uploadUrl = BASE_URL + '/upload'

        console.log('[上传] 开始上传:', {
          url: uploadUrl,
          filePath: compressedPath,
          bizType: bizType,
          hasToken: !!token
        })

        wx.uploadFile({
          url: uploadUrl,
          filePath: compressedPath,
          name: 'file',
          header: {
            'Authorization': token ? 'Bearer ' + token : ''
          },
          formData: {
            type: bizType
          },
          success: (res) => {
            console.log('[上传] 响应成功:', {
              statusCode: res.statusCode,
              data: res.data
            })
            try {
              const data = JSON.parse(res.data)
              if (data.code === 0 && data.data && data.data.url) {
                // 拼接完整 URL
                const url = data.data.url
                if (url.startsWith('http')) {
                  resolve(url)
                } else {
                  // 相对路径，拼接 BASE_URL 前缀
                  const base = BASE_URL.replace(/\/api$/, '')
                  resolve(base + url)
                }
              } else {
                const errMsg = data.msg || '上传失败'
                console.error('[上传] 业务错误:', errMsg, data)
                reject(new Error(errMsg))
              }
            } catch (e) {
              console.error('[上传] 响应解析失败:', e, '原始数据:', res.data)
              reject(new Error('上传响应解析失败'))
            }
          },
          fail: (err) => {
            console.error('[上传] 请求失败:', err)
            reject(err)
          }
        })
      })
    })
  },

  // 批量上传文件（串行上传，避免并发太多导致失败）
  uploadFiles(filePaths, bizType = 'general') {
    if (!USE_REMOTE) {
      return Promise.resolve(filePaths)
    }
    // 串行上传，一张一张来
    return filePaths.reduce((promise, path) => {
      return promise.then(results => {
        return this.uploadFile(path, bizType).then(url => {
          results.push(url)
          return results
        })
      })
    }, Promise.resolve([]))
  }
}

// ==================== 用户相关 ====================
const userApi = {
  // 获取当前登录用户（远程模式下从后端拉取最新信息并更新缓存）
  getCurrentUser(forceRefresh = false) {
    const localUser = wx.getStorageSync('userInfo') || null
    // 本地模式或不强制刷新时，直接返回缓存
    if (!USE_REMOTE || !forceRefresh) {
      return Promise.resolve(localUser)
    }
    // 远程模式下，从后端拉取最新用户信息
    const token = getToken()
    if (!token) {
      return Promise.resolve(null)
    }
    return request({ url: '/user/profile' })
      .then(userInfo => {
        if (userInfo) {
          wx.setStorageSync('userInfo', userInfo)
        }
        return userInfo
      })
      .catch(() => {
        // 拉取失败时返回本地缓存，不影响使用
        return localUser
      })
  },

  // 保存用户信息到本地
  saveUserInfo(userInfo) {
    wx.setStorageSync('userInfo', userInfo)
    return Promise.resolve(userInfo)
  },

  // 退出登录
  logout() {
    wx.removeStorageSync('userInfo')
    wx.removeStorageSync('token')
    return Promise.resolve()
  },

  // 获取用户类型
  getUserType() {
    const user = wx.getStorageSync('userInfo')
    return Promise.resolve(user ? (user.userType || 0) : 0)
  },

  // 设置用户类型
  setUserType(userType) {
    const user = wx.getStorageSync('userInfo') || {}
    user.userType = userType
    wx.setStorageSync('userInfo', user)
    return Promise.resolve(user)
  },

  // ============ 以下是后端接口（USE_REMOTE=true 时生效） ============

  // 微信登录（获取 openid + token）
  login(code, userInfo) {
    if (USE_REMOTE) {
      return request({
        url: '/user/login',
        method: 'POST',
        data: { code, userInfo }
      }).then(res => {
        if (res.token) setToken(res.token)
        if (res.userInfo) this.saveUserInfo(res.userInfo)
        return res
      })
    }
    // 本地模式：模拟登录
    return new Promise((resolve) => {
      const user = {
        userId: utils.generateId('UID'),
        nickName: userInfo?.nickName || '微信用户',
        avatarUrl: userInfo?.avatarUrl || '',
        userType: 0
      }
      setToken('mock_token_' + user.userId)
      this.saveUserInfo(user)
      resolve({ userInfo: user, token: 'mock_token' })
    })
  },

  // 更新用户头像昵称
  updateProfile(data) {
    if (USE_REMOTE) {
      return request({
        url: '/user/profile',
        method: 'PUT',
        data
      }).then(res => {
        if (res) this.saveUserInfo(res)
        return res
      })
    }
    // 本地模式
    return new Promise((resolve) => {
      const user = wx.getStorageSync('userInfo') || {}
      const updated = { ...user, ...data }
      this.saveUserInfo(updated)
      // 同步更新 allUsers
      const allUsers = wx.getStorageSync('allUsers') || []
      const idx = allUsers.findIndex(u => u.userId === updated.userId)
      if (idx > -1) allUsers[idx] = updated
      else allUsers.push(updated)
      wx.setStorageSync('allUsers', allUsers)
      resolve(updated)
    })
  },

  // ============ 用户钱包 ============

  // 获取用户钱包余额
  getWallet(userId) {
    if (USE_REMOTE) {
      return request({ url: `/user/wallet?userId=${userId}` })
    }
    // 本地模式
    return new Promise(resolve => {
      const wallets = wx.getStorageSync('userWallets') || {}
      const wallet = wallets[userId] || { balance: 0, totalRecharge: 0, totalSpend: 0 }
      resolve(wallet)
    })
  },

  // 用户钱包扣款（原子操作，余额不足返回失败）
  deductBalance(userId, amount, title = '', orderId = '') {
    if (USE_REMOTE) {
      return request({
        url: '/user/wallet/deduct',
        method: 'POST',
        data: { userId, amount, title, orderId }
      })
    }
    // 本地模式：原子扣款
    return new Promise(resolve => {
      const wallets = wx.getStorageSync('userWallets') || {}
      const wallet = wallets[userId] || { balance: 0, totalRecharge: 0, totalSpend: 0 }
      const amt = parseFloat(amount) || 0

      if (amt <= 0) {
        resolve({ success: false, message: '金额无效' })
        return
      }
      if (wallet.balance < amt) {
        resolve({ success: false, message: '余额不足，请先充值' })
        return
      }

      // 扣款
      wallet.balance = Number((wallet.balance - amt).toFixed(2))
      wallet.totalSpend = Number((wallet.totalSpend + amt).toFixed(2))
      wallets[userId] = wallet
      wx.setStorageSync('userWallets', wallets)

      // 记录流水
      const flows = wx.getStorageSync('userBalanceFlows_' + userId) || []
      flows.unshift({
        id: utils.generateId('FLW'),
        type: 2, // 1=收入 2=支出
        amount: amt,
        title: title || '订单支付',
        orderId: orderId,
        balanceAfter: wallet.balance,
        createTime: utils.now()
      })
      wx.setStorageSync('userBalanceFlows_' + userId, flows)

      resolve({ success: true, balance: wallet.balance })
    })
  },

  // 用户钱包充值
  rechargeBalance(userId, amount) {
    if (USE_REMOTE) {
      return request({
        url: '/user/wallet/recharge',
        method: 'POST',
        data: { userId, amount }
      })
    }
    // 本地模式
    return new Promise(resolve => {
      const wallets = wx.getStorageSync('userWallets') || {}
      const wallet = wallets[userId] || { balance: 0, totalRecharge: 0, totalSpend: 0 }
      const amt = parseFloat(amount) || 0

      if (amt <= 0) {
        resolve({ success: false, message: '金额无效' })
        return
      }

      wallet.balance = Number((wallet.balance + amt).toFixed(2))
      wallet.totalRecharge = Number((wallet.totalRecharge + amt).toFixed(2))
      wallets[userId] = wallet
      wx.setStorageSync('userWallets', wallets)

      // 记录流水
      const flows = wx.getStorageSync('userBalanceFlows_' + userId) || []
      flows.unshift({
        id: utils.generateId('FLW'),
        type: 1,
        amount: amt,
        title: '钱包充值',
        orderId: '',
        balanceAfter: wallet.balance,
        createTime: utils.now()
      })
      wx.setStorageSync('userBalanceFlows_' + userId, flows)

      resolve({ success: true, balance: wallet.balance })
    })
  },

  // 获取用户余额流水
  getBalanceFlows(userId, page = 1, pageSize = 20) {
    if (USE_REMOTE) {
      return request({ url: `/user/wallet/flows?userId=${userId}&page=${page}&pageSize=${pageSize}` })
    }
    // 本地模式
    return new Promise(resolve => {
      const flows = wx.getStorageSync('userBalanceFlows_' + userId) || []
      const start = (page - 1) * pageSize
      const list = flows.slice(start, start + pageSize)
      resolve({ list, total: flows.length, page, pageSize })
    })
  },

  // 退款（订单取消时退回到钱包）
  refundBalance(userId, amount, title = '', orderId = '') {
    if (USE_REMOTE) {
      return request({
        url: '/user/wallet/refund',
        method: 'POST',
        data: { userId, amount, title, orderId }
      })
    }
    // 本地模式
    return new Promise(resolve => {
      const wallets = wx.getStorageSync('userWallets') || {}
      const wallet = wallets[userId] || { balance: 0, totalRecharge: 0, totalSpend: 0 }
      const amt = parseFloat(amount) || 0

      if (amt <= 0) {
        resolve({ success: false, message: '金额无效' })
        return
      }

      wallet.balance = Number((wallet.balance + amt).toFixed(2))
      wallet.totalSpend = Number(Math.max(0, wallet.totalSpend - amt).toFixed(2))
      wallets[userId] = wallet
      wx.setStorageSync('userWallets', wallets)

      // 记录流水
      const flows = wx.getStorageSync('userBalanceFlows_' + userId) || []
      flows.unshift({
        id: utils.generateId('FLW'),
        type: 1,
        amount: amt,
        title: title || '订单退款',
        orderId: orderId,
        balanceAfter: wallet.balance,
        createTime: utils.now()
      })
      wx.setStorageSync('userBalanceFlows_' + userId, flows)

      resolve({ success: true, balance: wallet.balance })
    })
  },

}

// ==================== 订单相关 ====================
const orderApi = {
  // 获取用户订单列表
  // 支持三种调用方式：
  //   getUserOrders(userId) - 旧方式
  //   getUserOrders(userId, options) - 新方式，options: { status, page, pageSize }
  //   getUserOrders(options) - options: { status, page, pageSize }
  getUserOrders(userId, options) {
    // 参数解析：兼容多种调用方式
    let uid = userId
    let opts = options || {}
    if (typeof userId === 'object' && userId !== null) {
      uid = null
      opts = userId
    }
    const { status, page = 1, pageSize = 10 } = opts

    if (USE_REMOTE) {
      const data = {}
      if (uid) data.userId = uid
      if (status !== undefined && status !== null && status !== '') data.status = status
      if (page) data.page = page
      if (pageSize) data.pageSize = pageSize
      return request({ url: '/orders', data })
    }
    // 本地模式
    return new Promise(resolve => {
      let all = wx.getStorageSync('orders') || []
      // 按 userId 过滤
      if (uid) {
        all = all.filter(o => o.userId === uid)
      }
      // 按 status 过滤
      if (status !== undefined && status !== null && status !== '') {
        const s = typeof status === 'number' ? status : STATUS_TEXT_TO_NUM[status]
        if (s !== undefined) {
          all = all.filter(o => o.status === s)
        }
      }
      // 按 createTime 倒序排序
      all.sort((a, b) => Number(b.createTime || 0) - Number(a.createTime || 0))
      // 分页
      resolve(paginateList(all, page, pageSize))
    })
  },

  // 获取护航订单列表
  // 支持两种调用方式：
  //   getEscortOrders(escortId) - 旧方式
  //   getEscortOrders(escortId, options) - 新方式，options: { status, page, pageSize }
  getEscortOrders(escortId, options) {
    const opts = options || {}
    const { status, page = 1, pageSize = 10 } = opts

    if (USE_REMOTE) {
      const data = {}
      if (escortId) data.escortId = escortId
      if (status !== undefined && status !== null && status !== '') data.status = status
      if (page) data.page = page
      if (pageSize) data.pageSize = pageSize
      return request({ url: '/escort/orders', data })
    }
    // 本地模式
    return new Promise(resolve => {
      let all = wx.getStorageSync('orders') || []
      // 按 escortId 过滤
      if (escortId) {
        all = all.filter(o => o.escortId === escortId)
      }
      // 按 status 过滤
      if (status !== undefined && status !== null && status !== '') {
        const s = typeof status === 'number' ? status : STATUS_TEXT_TO_NUM[status]
        if (s !== undefined) {
          all = all.filter(o => o.status === s)
        }
      }
      // 按 createTime 倒序排序
      all.sort((a, b) => Number(b.createTime || 0) - Number(a.createTime || 0))
      // 分页
      resolve(paginateList(all, page, pageSize))
    })
  },

  // 获取打手自己的订单详情（按 escort_openid 查询）
  getEscortOrderDetail(orderId) {
    if (USE_REMOTE) {
      return request({ url: `/escort/orders/${orderId}` })
    }
    return new Promise(resolve => {
      const orders = wx.getStorageSync('orders') || []
      resolve(orders.find(o => o.orderId === orderId || o.id == orderId) || null)
    })
  },

  // 获取可抢订单列表
  // 支持分页：getAvailableOrders(options) - options: { page, pageSize }
  getAvailableOrders(options) {
    const opts = options || {}
    const { page = 1, pageSize = 10 } = opts

    if (USE_REMOTE) {
      return request({
        url: '/orders/available',
        data: { page, pageSize }
      })
    }
    // 本地模式
    return new Promise(resolve => {
      const all = wx.getStorageSync('orders') || []
      // 过滤待接单且无护航的订单
      let filtered = all.filter(o => o.status === ORDER_STATUS.PENDING && !o.escortId)
      // 按 createTime 倒序排序
      filtered.sort((a, b) => Number(b.createTime || 0) - Number(a.createTime || 0))
      // 分页
      resolve(paginateList(filtered, page, pageSize))
    })
  },

  // 获取订单详情
  getOrderDetail(orderId) {
    if (USE_REMOTE) {
      return request({ url: `/orders/${orderId}` })
    }
    return new Promise(resolve => {
      const orders = wx.getStorageSync('orders') || []
      resolve(orders.find(o => o.orderId === orderId) || null)
    })
  },

  // 创建订单
  createOrder(order) {
    if (!order.userId) {
      return Promise.reject({ message: '请先登录' })
    }
    if (USE_REMOTE) {
      return request({ url: '/orders', method: 'POST', data: order })
    }
    return new Promise(resolve => {
      const orders = wx.getStorageSync('orders') || []
      const newOrder = {
        ...order,
        orderId: order.orderId || utils.generateId('ORD'),
        status: ORDER_STATUS.PENDING,
        statusText: '待接单',
        createTime: utils.now()
      }
      orders.push(newOrder)
      wx.setStorageSync('orders', orders)
      resolve(newOrder)
    })
  },

  // 原子更新订单状态
  // expectedStatus: 期望的当前状态（数字或数字数组），传入后会在写入前再次校验，不匹配则返回 null
  // 用法：_updateOrderStatus(orderId, targetStatus, statusText, extraData, expectedStatus)
  _updateOrderStatus(orderId, status, statusText, extraData = {}, expectedStatus = null) {
    const orders = wx.getStorageSync('orders') || []
    const idx = orders.findIndex(o => o.orderId === orderId)
    if (idx === -1) return null

    // 原子性校验：如果传入了期望状态，先校验再写入
    if (expectedStatus !== null) {
      const currentStatus = orders[idx].status
      if (Array.isArray(expectedStatus)) {
        if (!expectedStatus.includes(currentStatus)) return null
      } else {
        if (currentStatus !== expectedStatus) return null
      }
    }

    orders[idx] = { ...orders[idx], status, statusText, ...extraData }
    wx.setStorageSync('orders', orders)
    return orders[idx]
  },

  // 校验状态流转
  _canTransition(currentStatus, targetStatus) {
    const allowed = ORDER_STATUS_FLOW[currentStatus]
    return allowed && allowed.includes(targetStatus)
  },

  // 用户取消订单
  cancelOrder(orderId) {
    if (USE_REMOTE) {
      return request({ url: `/orders/${orderId}/cancel`, method: 'POST' })
    }
    // 本地模式：原子更新，仅待接单状态可取消，取消后自动退款
    return new Promise((resolve) => {
      // 1. 先读订单详情（获取 userId 和金额）
      const orders = wx.getStorageSync('orders') || []
      const order = orders.find(o => o.orderId === orderId)
      if (!order) {
        resolve({ success: false, message: '订单不存在' })
        return
      }

      // 2. 原子更新状态
      const result = this._updateOrderStatus(
        orderId,
        ORDER_STATUS.CANCELLED,
        '已取消',
        { cancelTime: utils.now() },
        ORDER_STATUS.PENDING  // 仅当当前状态为待接单时才允许取消
      )

      if (!result) {
        resolve({ success: false, message: '当前订单状态无法取消' })
        return
      }

      // 3. 状态更新成功，如果订单已支付则退款
      if (result.paid && result.userId && parseFloat(result.totalPrice) > 0) {
        userApi.refundBalance(
          result.userId,
          result.totalPrice,
          '订单取消退款',
          orderId
        ).then(() => {
          resolve({ success: true, order: result })
        })
      } else {
        resolve({ success: true, order: result })
      }
    })
  },

  // 护航接单
  takeOrder(orderId, escortId, escortName, escortProfile = null) {
    if (USE_REMOTE) {
      return request({
        url: `/escort/orders/${orderId}/take`,
        method: 'POST',
        data: { escortProfile }
      })
    }
    // 本地模式：原子抢单
    return new Promise((resolve) => {
      // 先检查进行中订单数量
      this.getEscortOrders(escortId).then(result => {
        const ordersList = result.list || result
        const activeCount = ordersList.filter(o =>
          o.status === ORDER_STATUS.IN_PROGRESS ||
          o.status === ORDER_STATUS.IN_SERVICE ||
          o.status === ORDER_STATUS.TO_CONFIRM
        ).length
        if (activeCount >= GRAB_CONFIG.MAX_ACTIVE_ORDERS) {
          resolve({ success: false, message: `进行中订单已达${GRAB_CONFIG.MAX_ACTIVE_ORDERS}单上限，请先完成当前订单` })
          return
        }

        // 原子性抢单：只有待接单且无护航的订单才能被抢走
        const orders = wx.getStorageSync('orders') || []
        const idx = orders.findIndex(o => o.orderId === orderId)
        if (idx === -1) {
          resolve({ success: false, message: '订单不存在' })
          return
        }
        // 写入前最终校验（原子性保障）
        if (orders[idx].status !== ORDER_STATUS.PENDING || orders[idx].escortId) {
          resolve({ success: false, message: '手慢了，订单已被抢走' })
          return
        }

        orders[idx] = {
          ...orders[idx],
          status: ORDER_STATUS.IN_PROGRESS,
          statusText: '进行中',
          escortId,
          escortName,
          escortProfile,
          takeTime: utils.now()
        }
        wx.setStorageSync('orders', orders)
        resolve({ success: true, order: orders[idx] })
      })
    })
  },

  // 开始服务
  startService(orderId) {
    if (USE_REMOTE) {
      return request({ url: `/escort/orders/${orderId}/start`, method: 'POST' })
    }
    // 本地模式：原子更新，仅进行中状态可开始服务
    return new Promise((resolve) => {
      const result = this._updateOrderStatus(
        orderId,
        ORDER_STATUS.IN_SERVICE,
        '服务中',
        { startTime: utils.now() },
        ORDER_STATUS.IN_PROGRESS  // 仅当当前状态为进行中时才允许开始服务
      )
      resolve({ success: !!result, order: result, message: result ? '' : '当前状态无法开始服务' })
    })
  },

  // 提交完成申请
  submitComplete(orderId, photos = [], remark = '') {
    if (USE_REMOTE) {
      return request({
        url: `/escort/orders/${orderId}/complete`,
        method: 'POST',
        data: { photos, remark }
      })
    }
    // 本地模式：原子更新，仅服务中状态可提交完成
    return new Promise((resolve) => {
      const result = this._updateOrderStatus(
        orderId,
        ORDER_STATUS.TO_CONFIRM,
        '待确认',
        {
          completePhotos: photos,
          completeRemark: remark,
          submitCompleteTime: utils.now()
        },
        ORDER_STATUS.IN_SERVICE  // 仅当当前状态为服务中时才允许提交完成
      )
      resolve({ success: !!result, order: result, message: result ? '' : '当前状态无法提交完成' })
    })
  },

  // 用户确认完成（触发佣金结算，幂等：重复调用不会重复结算）
  confirmComplete(orderId) {
    if (USE_REMOTE) {
      return request({
        url: `/orders/${orderId}/confirm`,
        method: 'POST'
      })
    }
    // 本地模式：原子更新 + 幂等结算
    return new Promise((resolve) => {
      // 1. 先原子性更新订单状态（待确认 → 已完成）
      const result = this._updateOrderStatus(
        orderId,
        ORDER_STATUS.COMPLETED,
        '已完成',
        { completeTime: utils.now() },
        ORDER_STATUS.TO_CONFIRM  // 仅当当前状态为待确认时才允许确认完成
      )

      if (!result) {
        // 可能已经是已完成状态，检查是否已结算
        const orders = wx.getStorageSync('orders') || []
        const order = orders.find(o => o.orderId === orderId)
        if (order && order.status === ORDER_STATUS.COMPLETED) {
          // 已完成状态，但不确定是否已结算，做幂等检查
          if (order.settled) {
            resolve({ success: true, order, message: '订单已确认完成', alreadyConfirmed: true })
          } else {
            // 状态已完成但未结算（异常情况），补结算
            this._doSettlement(order).then(() => {
              resolve({ success: true, order, message: '订单已确认完成' })
            })
          }
        } else {
          resolve({ success: false, message: '当前状态无法确认完成' })
        }
        return
      }

      // 2. 状态更新成功，执行佣金结算（幂等：通过 settled 标记保证只执行一次）
      this._doSettlement(result).then(() => {
        resolve({ success: true, order: result, message: '' })
      })
    })
  },

  // 内部：执行佣金结算（幂等：先检查 settled 标记）
  _doSettlement(order) {
    return new Promise((resolve) => {
      if (!order || !order.escortId) {
        resolve()
        return
      }

      // 幂等检查：先读订单再写，确保只结算一次
      const orders = wx.getStorageSync('orders') || []
      const idx = orders.findIndex(o => o.orderId === order.orderId)
      if (idx === -1) { resolve(); return }
      if (orders[idx].settled) {
        // 已经结算过了，直接返回
        resolve()
        return
      }

      const amount = parseFloat(orders[idx].totalPrice || 0)
      const earnAmount = amount * PLATFORM_COMMISSION

      // 执行结算：加收益 + 加结算记录 + 加余额流水
      Promise.all([
        escortApi.addEarning(orders[idx].escortId, earnAmount),
        escortApi.addSettlement(orders[idx].escortId, earnAmount),
        escortApi.addBalanceFlow(orders[idx].escortId, 1, earnAmount, orders[idx].serviceName || '订单收益', orders[idx].orderId)
      ]).then(() => {
        // 标记为已结算（幂等标记）
        orders[idx].settled = true
        orders[idx].settleTime = utils.now()
        wx.setStorageSync('orders', orders)
        resolve()
      })
    })
  },

  // 护航退单
  escortCancelOrder(orderId, reason = '') {
    if (USE_REMOTE) {
      return request({
        url: `/escort/orders/${orderId}/cancel`,
        method: 'POST',
        data: { reason }
      })
    }
    // 本地模式：原子更新，进行中或服务中可退单
    return new Promise((resolve) => {
      const result = this._updateOrderStatus(
        orderId,
        ORDER_STATUS.PENDING,
        '待接单（护航已退单）',
        {
          escortId: '',
          escortName: '',
          escortProfile: null,
          takeTime: null,
          startTime: null,
          escortCancelReason: reason,
          escortCancelTime: utils.now(),
          hasEscortCancelled: true
        },
        [ORDER_STATUS.IN_PROGRESS, ORDER_STATUS.IN_SERVICE]  // 进行中或服务中都可退单
      )
      resolve({ success: !!result, order: result, message: result ? '' : '当前状态无法退单' })
    })
  }
}

// ==================== 收藏相关 ====================
const favoriteApi = {
  _getKey(userId) {
    return 'favorites_' + (userId || 'guest')
  },

  getFavorites(userId) {
    if (USE_REMOTE) {
      return request({ url: '/favorites' })
    }
    return new Promise(resolve => {
      const uid = userId || (wx.getStorageSync('userInfo') || {}).userId || 'guest'
      resolve(wx.getStorageSync(this._getKey(uid)) || [])
    })
  },

  addFavorite(service, userId) {
    if (USE_REMOTE) {
      return request({
        url: '/favorites',
        method: 'POST',
        data: { serviceId: service.id, service }
      })
    }
    return new Promise(resolve => {
      const uid = userId || (wx.getStorageSync('userInfo') || {}).userId || 'guest'
      const list = wx.getStorageSync(this._getKey(uid)) || []
      const serviceId = String(service.id)
      const exists = list.find(f => String(f.id) === serviceId)
      if (!exists) {
        list.push({ ...service, id: serviceId })
        wx.setStorageSync(this._getKey(uid), list)
      }
      resolve(list)
    })
  },

  removeFavorite(serviceId, userId) {
    if (USE_REMOTE) {
      return request({
        url: `/favorites/${serviceId}`,
        method: 'DELETE'
      })
    }
    return new Promise(resolve => {
      const uid = userId || (wx.getStorageSync('userInfo') || {}).userId || 'guest'
      let list = wx.getStorageSync(this._getKey(uid)) || []
      const targetId = String(serviceId)
      list = list.filter(f => String(f.id) !== targetId)
      wx.setStorageSync(this._getKey(uid), list)
      resolve(list)
    })
  },

  isFavorited(serviceId, userId) {
    if (USE_REMOTE) {
      return request({ url: `/favorites/check`, data: { serviceId } })
    }
    return new Promise(resolve => {
      const uid = userId || (wx.getStorageSync('userInfo') || {}).userId || 'guest'
      const list = wx.getStorageSync(this._getKey(uid)) || []
      const targetId = String(serviceId)
      resolve(list.some(f => String(f.id) === targetId))
    })
  }
}

// ==================== 钱包相关 ====================
// walletApi 已统一使用 userApi 钱包接口，避免两套钱包数据不互通
const walletApi = {
  getWallet() {
    // 统一走 /user/wallet 接口，storage key 与 userApi 一致
    if (USE_REMOTE) {
      return request({ url: '/user/wallet' })
    }
    return new Promise(resolve => {
      const wallets = wx.getStorageSync('userWallets') || {}
      const user = wx.getStorageSync('userInfo') || {}
      const wallet = wallets[user.userId || 'guest'] || { balance: 0, totalRecharge: 0, totalSpend: 0 }
      resolve(wallet)
    })
  },

  recharge(amount) {
    if (!amount || amount <= 0) {
      return Promise.reject({ message: '充值金额无效' })
    }
    // 统一调用 /user/wallet/recharge（后端真实存在）
    if (USE_REMOTE) {
      return request({
        url: '/user/wallet/recharge',
        method: 'POST',
        data: { amount }
      })
    }
    return new Promise(resolve => {
      const wallets = wx.getStorageSync('userWallets') || {}
      const user = wx.getStorageSync('userInfo') || {}
      const uid = user.userId || 'guest'
      const wallet = wallets[uid] || { balance: 0, totalRecharge: 0, totalSpend: 0 }
      wallet.balance = parseFloat(wallet.balance) + amount
      wallet.totalRecharge = parseFloat(wallet.totalRecharge || 0) + amount
      wallets[uid] = wallet
      wx.setStorageSync('userWallets', wallets)

      const flows = wx.getStorageSync('userBalanceFlows_' + uid) || []
      flows.unshift({
        id: utils.generateId('FLW'),
        type: 1,
        amount: amount,
        title: '钱包充值',
        orderId: '',
        balanceAfter: wallet.balance,
        createTime: utils.now()
      })
      wx.setStorageSync('userBalanceFlows_' + uid, flows)
      resolve(wallet)
    })
  },

  getRecords(options) {
    const opts = options || {}
    const { page = 1, pageSize = 10 } = opts

    // 统一调用 /user/wallet/flows
    if (USE_REMOTE) {
      return request({
        url: '/user/wallet/flows',
        data: { page, pageSize }
      })
    }
    return new Promise(resolve => {
      const user = wx.getStorageSync('userInfo') || {}
      const uid = user.userId || 'guest'
      const all = wx.getStorageSync('userBalanceFlows_' + uid) || []
      all.sort((a, b) => Number(b.createTime || 0) - Number(a.createTime || 0))
      resolve(paginateList(all, page, pageSize))
    })
  },

  getFlows(options) {
    return this.getRecords(options)
  }
}

// ==================== 护航申请相关 ====================
const applyApi = {
  LIMIT_CONFIG: {
    maxCancelCount: 3,
    limitDays: 30,
    banDays: 30
  },

  submitApply(applyData) {
    if (USE_REMOTE) {
      return request({
        url: '/escort/apply',
        method: 'POST',
        data: applyData
      })
    }
    return new Promise(resolve => {
      const applies = wx.getStorageSync('joinApplies') || []
      const newApply = {
        id: utils.generateId('APPLY'),
        ...applyData,
        status: APPLY_STATUS.PENDING,
        statusText: '审核中',
        createTime: utils.now()
      }
      applies.push(newApply)
      wx.setStorageSync('joinApplies', applies)
      resolve(newApply)
    })
  },

  getUserApply(userId) {
    if (USE_REMOTE) {
      return request({ url: '/escort/apply/latest' })
    }
    return new Promise(resolve => {
      const applies = wx.getStorageSync('joinApplies') || []
      const userApplies = applies.filter(a => a.userId === userId)
      if (userApplies.length === 0) resolve(null)
      else resolve(userApplies[userApplies.length - 1])
    })
  },

  getUserAllApplies(userId) {
    if (USE_REMOTE) {
      return request({ url: '/escort/applies' })
    }
    return new Promise(resolve => {
      const applies = wx.getStorageSync('joinApplies') || []
      resolve(applies.filter(a => a.userId === userId))
    })
  },

  cancelApply(applyId) {
    if (USE_REMOTE) {
      return request({ url: `/escort/apply/${applyId}/cancel`, method: 'POST' })
    }
    return new Promise(resolve => {
      const applies = wx.getStorageSync('joinApplies') || []
      const idx = applies.findIndex(a => a.id === applyId)
      if (idx > -1 && applies[idx].status === APPLY_STATUS.PENDING) {
        applies[idx].status = APPLY_STATUS.CANCELLED
        applies[idx].statusText = '已取消'
        applies[idx].cancelTime = utils.now()
        wx.setStorageSync('joinApplies', applies)
        resolve(applies[idx])
      } else {
        resolve(null)
      }
    })
  },

  checkBanStatus(userId) {
    if (USE_REMOTE) {
      return request({ url: '/escort/apply/ban-status' })
    }
    return new Promise(resolve => {
      this.getUserAllApplies(userId).then(userApplies => {
        if (userApplies.length === 0) {
          resolve({ banned: false, count: 0, banEndTime: '', reason: '' })
          return
        }

        const now = utils.now()
        const limitMs = this.LIMIT_CONFIG.limitDays * 24 * 60 * 60 * 1000

        let cancelCount = 0
        userApplies.forEach(a => {
          if (a.status === APPLY_STATUS.CANCELLED && a.cancelTime) {
            if (now - Number(a.cancelTime) < limitMs) cancelCount++
          } else if (a.status === APPLY_STATUS.REJECTED && a.auditTime) {
            if (now - Number(a.auditTime) < limitMs) cancelCount++
          }
        })

        if (cancelCount >= this.LIMIT_CONFIG.maxCancelCount) {
          let lastCancelTime = 0
          userApplies.forEach(a => {
            let time = 0
            if (a.status === APPLY_STATUS.CANCELLED && a.cancelTime) time = Number(a.cancelTime)
            else if (a.status === APPLY_STATUS.REJECTED && a.auditTime) time = Number(a.auditTime)
            if (time > lastCancelTime) lastCancelTime = time
          })

          const banEndTime = lastCancelTime + this.LIMIT_CONFIG.banDays * 24 * 60 * 60 * 1000
          if (now < banEndTime) {
            resolve({
              banned: true,
              count: cancelCount,
              banEndTime: utils.formatDate(banEndTime),
              reason: `30天内取消/被拒达到${this.LIMIT_CONFIG.maxCancelCount}次，已封禁${this.LIMIT_CONFIG.banDays}天`
            })
            return
          }
        }

        resolve({ banned: false, count: cancelCount, banEndTime: '', reason: '' })
      })
    })
  }
}

// ==================== 护航收益相关 ====================
const escortApi = {
  getEscortWallet(escortId) {
    if (USE_REMOTE) {
      return request({ url: '/escort/wallet' })
    }
    return new Promise(resolve => {
      const key = 'escortWallet_' + escortId
      resolve(wx.getStorageSync(key) || { available: 0, totalWithdraw: 0, totalEarn: 0 })
    })
  },

  addEarning(escortId, amount) {
    if (USE_REMOTE) {
      return Promise.resolve() // 后端处理
    }
    return new Promise(resolve => {
      const key = 'escortWallet_' + escortId
      const wallet = wx.getStorageSync(key) || { available: 0, totalWithdraw: 0, totalEarn: 0 }
      wallet.available = parseFloat(wallet.available) + amount
      wallet.totalEarn = parseFloat(wallet.totalEarn) + amount
      wx.setStorageSync(key, wallet)
      resolve(wallet)
    })
  },

  withdraw(escortId, amount) {
    if (USE_REMOTE) {
      return request({
        url: '/escort/wallet/withdraw',
        method: 'POST',
        data: { amount }
      })
    }
    return new Promise((resolve, reject) => {
      const key = 'escortWallet_' + escortId
      const wallet = wx.getStorageSync(key) || { available: 0, totalWithdraw: 0, totalEarn: 0 }
      if (parseFloat(wallet.available) < amount) {
        reject(new Error('余额不足'))
        return
      }
      wallet.available = parseFloat(wallet.available) - amount
      wallet.totalWithdraw = parseFloat(wallet.totalWithdraw) + amount
      wx.setStorageSync(key, wallet)

      const recordKey = 'escortWithdraw_' + escortId
      const records = wx.getStorageSync(recordKey) || []
      records.unshift({ amount, time: utils.now(), status: 0 })
      wx.setStorageSync(recordKey, records)
      resolve(wallet)
    })
  },

  getEscortStats(escortId) {
    if (USE_REMOTE) {
      return request({ url: '/escort/stats' })
    }
    return new Promise(resolve => {
      // 本地模式：直接从存储获取全部订单进行统计
      const all = wx.getStorageSync('orders') || []
      const orders = all.filter(o => o.escortId === escortId)
      const completedOrders = orders.filter(o => o.status === ORDER_STATUS.COMPLETED)
      resolve({
        pending: orders.filter(o => o.status === ORDER_STATUS.PENDING).length,
        inService: orders.filter(o => o.status === ORDER_STATUS.IN_PROGRESS || o.status === ORDER_STATUS.IN_SERVICE).length,
        todayCompleted: completedOrders.filter(o => o.completeTime && utils.isToday(o.completeTime)).length,
        todayJoined: orders.filter(o => o.takeTime && utils.isToday(o.takeTime)).length
      })
    })
  },

  // 获取收益统计
  getEarningsStats(escortId) {
    if (USE_REMOTE) {
      return request({ url: '/escort/earnings' })
    }
    return new Promise(resolve => {
      // 本地模式：直接从存储获取全部订单进行统计
      const all = wx.getStorageSync('orders') || []
      const orders = all.filter(o => o.escortId === escortId)
      const completedOrders = orders.filter(o => o.status === ORDER_STATUS.COMPLETED)
      const now = Date.now()
      const todayStart = utils.getDayStart(now)
      const yesterdayStart = todayStart - 24 * 60 * 60 * 1000
      const yesterdayEnd = todayStart
      const nowDate = new Date(now)
      const monthStart = new Date(nowDate.getFullYear(), nowDate.getMonth(), 1).getTime()

      const calcEarn = (list) => list.reduce((sum, o) => sum + parseFloat(o.totalPrice || 0) * PLATFORM_COMMISSION, 0)

      const todayList = completedOrders.filter(o => o.completeTime && Number(o.completeTime) >= todayStart)
      const yesterdayList = completedOrders.filter(o => o.completeTime && Number(o.completeTime) >= yesterdayStart && Number(o.completeTime) < yesterdayEnd)
      const monthList = completedOrders.filter(o => o.completeTime && Number(o.completeTime) >= monthStart)

      resolve({
        todayEarn: calcEarn(todayList).toFixed(2),
        yesterdayEarn: calcEarn(yesterdayList).toFixed(2),
        monthEarn: calcEarn(monthList).toFixed(2),
        totalEarn: calcEarn(completedOrders).toFixed(2),
        todayCount: todayList.length,
        yesterdayCount: yesterdayList.length,
        monthCount: monthList.length,
        totalCount: completedOrders.length
      })
    })
  },

  // 获取结算记录
  // 支持分页：getSettlementRecords(escortId, options) - options: { page, pageSize }
  getSettlementRecords(escortId, options) {
    const opts = options || {}
    const { page = 1, pageSize = 10 } = opts

    if (USE_REMOTE) {
      return request({
        url: '/escort/settlements',
        data: { page, pageSize }
      })
    }
    return new Promise(resolve => {
      const key = 'escortSettlement_' + escortId
      const all = wx.getStorageSync(key) || []
      // 按时间倒序排序
      all.sort((a, b) => Number(b.time || 0) - Number(a.time || 0))
      resolve(paginateList(all, page, pageSize))
    })
  },

  // 添加结算记录
  addSettlement(escortId, amount, mode = '汇付转账') {
    if (USE_REMOTE) {
      return Promise.resolve() // 后端处理
    }
    return new Promise(resolve => {
      const key = 'escortSettlement_' + escortId
      const records = wx.getStorageSync(key) || []
      const record = {
        id: utils.generateId('SET'),
        amount: amount.toFixed(2),
        time: utils.now(),
        mode: mode,
        status: 1
      }
      records.unshift(record)
      wx.setStorageSync(key, records)
      resolve(record)
    })
  },

  // 获取余额流水
  // 支持分页：getBalanceFlow(escortId, options) - options: { page, pageSize }
  getBalanceFlow(escortId, options) {
    const opts = options || {}
    const { page = 1, pageSize = 10 } = opts

    if (USE_REMOTE) {
      return request({
        url: '/escort/balance-flow',
        data: { page, pageSize }
      })
    }
    return new Promise(resolve => {
      const key = 'escortBalanceFlow_' + escortId
      const all = wx.getStorageSync(key) || []
      // 按时间倒序排序
      all.sort((a, b) => Number(b.time || 0) - Number(a.time || 0))
      resolve(paginateList(all, page, pageSize))
    })
  },

  // 添加余额流水
  addBalanceFlow(escortId, type, amount, title, orderId = '') {
    if (USE_REMOTE) {
      return Promise.resolve()
    }
    return new Promise(resolve => {
      const key = 'escortBalanceFlow_' + escortId
      const records = wx.getStorageSync(key) || []
      const record = {
        id: utils.generateId('FLOW'),
        orderId: orderId,
        title: title,
        type: type,
        amount: amount.toFixed(2),
        time: utils.now()
      }
      records.unshift(record)
      wx.setStorageSync(key, records)
      resolve(record)
    })
  },

  // 获取护航个人资料（公开资料，用于查看他人）
  getEscortProfile(escortId) {
    if (USE_REMOTE) {
      return request({ url: `/escort/profile/${escortId}` })
    }
    return new Promise(resolve => {
      const key = 'escortProfile_' + escortId
      resolve(wx.getStorageSync(key) || null)
    })
  },

  // 获取自己的护航资料（完整资料，包含审核中待生效的内容）
  getMyProfile() {
    if (USE_REMOTE) {
      return request({ url: '/escort/profile' })
    }
    return new Promise(resolve => {
      userApi.getCurrentUser().then(user => {
        if (!user || !user.userId) { resolve(null); return }
        const key = 'escortProfile_' + user.userId
        resolve(wx.getStorageSync(key) || null)
      })
    })
  },

  // 保存护航个人资料
  saveEscortProfile(escortId, profileData) {
    if (USE_REMOTE) {
      return request({
        url: '/escort/profile',
        method: 'PUT',
        data: profileData
      })
    }
    return new Promise(resolve => {
      const key = 'escortProfile_' + escortId
      const oldProfile = wx.getStorageSync(key) || null
      const newProfile = {
        ...oldProfile,
        ...profileData,
        escortId: escortId,
        updateTime: utils.now()
      }
      wx.setStorageSync(key, newProfile)
      resolve(newProfile)
    })
  },

  // 提交资料修改审核
  submitProfileAudit(escortId, profileData) {
    if (USE_REMOTE) {
      return request({
        url: '/escort/profile-audit',
        method: 'POST',
        data: profileData
      })
    }
    return new Promise(resolve => {
      const audits = wx.getStorageSync('profileAudits') || []
      const audit = {
        id: utils.generateId('PAUDIT'),
        escortId: escortId,
        profile: profileData,
        status: APPLY_STATUS.PENDING,
        statusText: '审核中',
        createTime: utils.now()
      }
      audits.unshift(audit)
      wx.setStorageSync('profileAudits', audits)
      resolve(audit)
    })
  },

  // 获取护航最新资料审核状态
  getLatestProfileAudit(escortId) {
    if (USE_REMOTE) {
      return request({ url: '/escort/profile-audit/latest' })
    }
    return new Promise(resolve => {
      const audits = wx.getStorageSync('profileAudits') || []
      const escortAudits = audits.filter(a => a.escortId === escortId)
      if (escortAudits.length === 0) resolve(null)
      else resolve(escortAudits[0])
    })
  },

  // 获取打手列表（邀请用）
  getEscortList(keyword) {
    if (USE_REMOTE) {
      const data = {}
      if (keyword) data.keyword = keyword
      return request({ url: '/escort/list', data })
    }
    return new Promise(resolve => {
      const escorts = wx.getStorageSync('escorts') || []
      let filtered = escorts
      if (keyword) {
        filtered = escorts.filter(e => (e.nickName || '').includes(keyword))
      }
      resolve({ list: filtered, total: filtered.length })
    })
  },

  // 邀请打手加入订单
  inviteTeamMembers(orderId, members) {
    if (USE_REMOTE) {
      return request({
        url: `/escort/orders/${orderId}/invite`,
        method: 'POST',
        data: { members }
      })
    }
    return new Promise(resolve => {
      resolve({ teamMembers: members })
    })
  },

  // 获取订单队伍成员
  getTeamMembers(orderId) {
    if (USE_REMOTE) {
      return request({ url: `/escort/orders/${orderId}/team` })
    }
    return new Promise(resolve => {
      resolve({ teamMembers: [] })
    })
  }
}

// ==================== 微信支付相关 ====================
const payApi = {
  // 统一下单（订单支付）— 保留兼容，实际不再使用
  unifiedOrder(orderId) {
    return request({
      url: '/pay/unifiedOrder',
      method: 'POST',
      data: { orderId, type: 'order' }
    })
  },

  // 虚拟支付下单（钱包充值）
  virtualRecharge(amount) {
    return request({
      url: '/pay/virtualOrder',
      method: 'POST',
      data: { amount }
    })
  },

  // 确认虚拟支付成功（前端支付成功后调用）
  virtualConfirm(outTradeNo) {
    return request({
      url: '/pay/virtualConfirm',
      method: 'POST',
      data: { outTradeNo }
    })
  },

  walletPay(orderId) {
    return request({
      url: '/pay/wallet-pay',
      method: 'POST',
      data: { orderId }
    })
  },

  // 调起虚拟支付
  requestVirtualPayment(payParams) {
    return new Promise((resolve, reject) => {
      wx.requestVirtualPayment({
        env: payParams.env,
        mode: payParams.mode,
        offerId: payParams.offerId,
        signData: payParams.signData,
        paySig: payParams.paySig,
        signature: payParams.signature,
        success: (res) => {
          if (res.errMsg === 'requestVirtualPayment:ok') {
            resolve(res)
          } else {
            reject(res)
          }
        },
        fail: reject
      })
    })
  },

  // 调起微信支付（保留兼容，mock 模式下直接跳过）
  requestPayment(payParams) {
    return new Promise((resolve, reject) => {
      if (payParams && payParams.mock) {
        resolve()
        return
      }
      wx.requestPayment({
        timeStamp: payParams.timeStamp,
        nonceStr: payParams.nonceStr,
        package: payParams.package,
        signType: payParams.signType,
        paySign: payParams.paySign,
        success: resolve,
        fail: reject
      })
    })
  }
}

// ==================== 接单公告 ====================

const announcementApi = {
  // 获取公告列表 + 未读数量（打手端）
  getLatest() {
    return request({ url: '/announcement/latest' })
  },

  // 标记公告已读
  markRead(annId) {
    return request({ url: '/announcement/read', method: 'POST', data: { id: annId } })
  }
}

module.exports = {
  // 配置
  BASE_URL,
  USE_REMOTE,
  // 常量
  ORDER_STATUS,
  APPLY_STATUS,
  USER_TYPE,
  PLATFORM_COMMISSION,
  GRAB_CONFIG,
  // API
  userApi,
  orderApi,
  favoriteApi,
  walletApi,
  payApi,
  applyApi,
  escortApi,
  announcementApi,
  utils
}
