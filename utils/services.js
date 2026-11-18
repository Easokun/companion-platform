// services.js - 统一服务数据配置
// 所有服务数据统一在这里维护，首页、分类页、下单页共用
// 支持从后端动态加载，本地硬编码作为兜底

// 补全图片URL（相对路径转完整URL）
function fixImageUrl(url) {
  if (!url) return ''
  if (url.startsWith('http')) return url
  // 本地静态资源路径直接返回
  if (url.startsWith('/images/')) return url
  // /uploads/xxx 之类的相对路径，拼接后端域名
  try {
    const api = require('./api')
    const base = api.BASE_URL.replace(/\/api$/, '')
    return base + url
  } catch (e) {
    return url
  }
}

// 标签颜色配置（统一管理）
const tagColors = {
  hot: 'linear-gradient(90deg, #FF6B6B, #FF8E8E)',
  value: 'linear-gradient(90deg, #4ECDC4, #6EE7DE)',
  new: 'linear-gradient(90deg, #A78BFA, #C4B5FD)',
  recommend: 'linear-gradient(90deg, #FBBF24, #FCD34D)',
  vip: 'linear-gradient(90deg, #7B61FF, #A78BFA)'
}

// 默认分类（兜底数据，后端不可用时使用）
const defaultCategories = [
  { id: 'cat1', name: '快乐游戏', icon: '🎮' },
  { id: 'cat2', name: '技术带飞', icon: '🚀' },
  { id: 'cat3', name: '王牌护航', icon: '🛡️' },
  { id: 'cat4', name: '专业陪玩', icon: '⚔️' },
  { id: 'cat5', name: '全程陪玩', icon: '💝' }
]

// 默认服务列表（兜底数据，后端不可用时使用）
const defaultServices = [
  // 快乐游戏暖心陪伴
  { id: 11, categoryId: 'cat1', tag: '热门', tagColor: tagColors.hot, name: '暖心陪玩', desc: '温柔陪伴，开心游戏', price: '30', image: '/images/logo.png', icon: '🎮' },
  { id: 12, categoryId: 'cat1', tag: '超值', tagColor: tagColors.value, name: '欢乐开黑', desc: '轻松提升，快乐游戏', price: '45', image: '/images/logo.png', icon: '🎮' },
  { id: 13, categoryId: 'cat1', tag: '新品', tagColor: tagColors.new, name: '语音连麦', desc: '全程语音，暖心陪伴', price: '50', image: '/images/logo.png', icon: '🎮' },
  { id: 14, categoryId: 'cat1', tag: '推荐', tagColor: tagColors.recommend, name: '新手教学', desc: '耐心指导，快速入门', price: '35', image: '/images/logo.png', icon: '🎮' },

  // 技术带飞稳赢提升
  { id: 21, categoryId: 'cat2', tag: '热门', tagColor: tagColors.hot, name: '段位护航', desc: '稳赢提升，快速冲段', price: '45', image: '/images/logo.png', icon: '🚀' },
  { id: 22, categoryId: 'cat2', tag: '超值', tagColor: tagColors.value, name: '排位陪玩', desc: '专业陪玩，高效提升', price: '68', image: '/images/logo.png', icon: '🚀' },
  { id: 23, categoryId: 'cat2', tag: '新品', tagColor: tagColors.new, name: '连胜套餐', desc: '保连胜，无忧提升', price: '108', image: '/images/logo.png', icon: '🚀' },
  { id: 24, categoryId: 'cat2', tag: '推荐', tagColor: tagColors.recommend, name: '巅峰赛', desc: '巅峰冲分，顶级技术', price: '128', image: '/images/logo.png', icon: '🚀' },

  // 王牌护航保底撤离
  { id: 31, categoryId: 'cat3', tag: '热门', tagColor: tagColors.hot, name: '绝密护航', desc: '全程语音陪同，100%安全撤离', price: '58', image: '/images/logo.png', icon: '🛡️' },
  { id: 32, categoryId: 'cat3', tag: '超值', tagColor: tagColors.value, name: '机密护航', desc: '高效清图，资源全带', price: '38', image: '/images/logo.png', icon: '🛡️' },
  { id: 33, categoryId: 'cat3', tag: '新品', tagColor: tagColors.new, name: '困难图护航', desc: '困难图保底，稳过', price: '88', image: '/images/logo.png', icon: '🛡️' },
  { id: 34, categoryId: 'cat3', tag: '推荐', tagColor: tagColors.recommend, name: '全图清图', desc: '全图清扫，不漏资源', price: '98', image: '/images/logo.png', icon: '🛡️' },

  // 专业陪玩极速提升
  { id: 41, categoryId: 'cat4', tag: '热门', tagColor: tagColors.hot, name: '极速提升', desc: '专业陪玩，极速冲刺', price: '35', image: '/images/logo.png', icon: '⚔️' },
  { id: 42, categoryId: 'cat4', tag: '超值', tagColor: tagColors.value, name: '代肝服务', desc: '纯手打，不碰账号资源', price: '25', image: '/images/logo.png', icon: '⚔️' },
  { id: 43, categoryId: 'cat4', tag: '新品', tagColor: tagColors.new, name: '任务代做', desc: '3x3任务、部门任务全包', price: '88', image: '/images/logo.png', icon: '⚔️' },
  { id: 44, categoryId: 'cat4', tag: '推荐', tagColor: tagColors.recommend, name: '日常全清', desc: '日常任务一站式搞定', price: '60', image: '/images/logo.png', icon: '⚔️' },

  // 安全高效全程陪玩
  { id: 51, categoryId: 'cat5', tag: 'VIP', tagColor: tagColors.vip, name: '包时护航', desc: '按小时计费，不限局数', price: '128', image: '/images/logo.png', icon: '💝' },
  { id: 52, categoryId: 'cat5', tag: '热门', tagColor: tagColors.hot, name: '全程陪玩', desc: '全程陪同，安全高效', price: '50', image: '/images/logo.png', icon: '💝' },
  { id: 53, categoryId: 'cat5', tag: '超值', tagColor: tagColors.value, name: '半日套餐', desc: '4小时专属陪玩', price: '180', image: '/images/logo.png', icon: '💝' },
  { id: 54, categoryId: 'cat5', tag: '推荐', tagColor: tagColors.recommend, name: '全日套餐', desc: '8小时全程护航', price: '320', image: '/images/logo.png', icon: '💝' }
]

// 当前生效的服务列表和分类（可被后端数据覆盖）
let allServices = [...defaultServices]
let categories = [...defaultCategories]

// ==================== 从后端加载数据 ====================

// 尝试从后端加载服务列表，成功则替换 allServices
function loadServicesFromServer() {
  const api = require('./api')
  if (!api.USE_REMOTE) {
    return Promise.resolve(false)
  }

  return new Promise((resolve) => {
    wx.request({
      url: api.BASE_URL + '/services',
      method: 'GET',
      timeout: 5000,
      success: (res) => {
        if (res.statusCode === 200 && res.data && res.data.code === 0 && Array.isArray(res.data.data)) {
          const serverData = res.data.data
          if (serverData.length > 0) {
            allServices = serverData.map(s => ({
              id: s.id,
              categoryId: s.categoryId || s.category_id,
              tag: s.tag || '',
              tagColor: s.tagColor || s.tag_color || '',
              name: s.name || '',
              desc: s.desc || s.description || '',
              price: String(s.price || '0'),
              image: fixImageUrl(s.image) || '/images/logo.png',
              icon: s.icon || ''
            }))
            console.log('[服务] 从后端加载', allServices.length, '个服务')
            resolve(true)
          } else {
            console.log('[服务] 后端返回空列表，使用本地数据')
            resolve(false)
          }
        } else {
          console.log('[服务] 后端响应异常，使用本地数据')
          resolve(false)
        }
      },
      fail: (err) => {
        console.log('[服务] 无法连接后端，使用本地数据', err)
        resolve(false)
      }
    })
  })
}

// 尝试从后端加载分类列表，成功则替换 categories
function loadCategoriesFromServer() {
  const api = require('./api')
  if (!api.USE_REMOTE) {
    return Promise.resolve(false)
  }

  return new Promise((resolve) => {
    wx.request({
      url: api.BASE_URL + '/services/categories',
      method: 'GET',
      timeout: 5000,
      success: (res) => {
        if (res.statusCode === 200 && res.data && res.data.code === 0 && Array.isArray(res.data.data)) {
          const serverCats = res.data.data
          if (serverCats.length > 0) {
            categories = serverCats.map(c => ({
              id: c.id || c.cat_id,
              name: c.name || '',
              icon: c.icon || ''
            }))
            console.log('[分类] 从后端加载', categories.length, '个分类')
            resolve(true)
          } else {
            console.log('[分类] 后端返回空列表，使用本地数据')
            resolve(false)
          }
        } else {
          console.log('[分类] 后端响应异常，使用本地数据')
          resolve(false)
        }
      },
      fail: (err) => {
        console.log('[分类] 无法连接后端，使用本地数据', err)
        resolve(false)
      }
    })
  })
}

// 从后端加载轮播图
function loadBannersFromServer() {
  const api = require('./api')
  if (!api.USE_REMOTE) {
    return Promise.resolve([])
  }

  return new Promise((resolve) => {
    wx.request({
      url: api.BASE_URL + '/banners',
      method: 'GET',
      timeout: 5000,
      success: (res) => {
        if (res.statusCode === 200 && res.data && res.data.code === 0 && Array.isArray(res.data.data)) {
          const banners = res.data.data.map(b => ({
            id: b.id,
            imageUrl: fixImageUrl(b.imageUrl || b.image_url || ''),
            linkUrl: b.linkUrl || b.link_url || ''
          }))
          console.log('[轮播图] 从后端加载', banners.length, '张')
          resolve(banners)
        } else {
          console.log('[轮播图] 后端响应异常')
          resolve([])
        }
      },
      fail: (err) => {
        console.log('[轮播图] 无法连接后端', err)
        resolve([])
      }
    })
  })
}

// 一次性加载所有后端数据
function loadAllFromServer() {
  return Promise.all([
    loadServicesFromServer(),
    loadCategoriesFromServer(),
    loadBannersFromServer()
  ]).then(([servicesOk, catsOk, banners]) => ({
    servicesLoaded: servicesOk,
    categoriesLoaded: catsOk,
    banners: banners
  }))
}

// ==================== 查询方法 ====================

// 根据分类ID获取服务列表
function getServicesByCategory(categoryId) {
  return allServices.filter(s => s.categoryId === categoryId)
}

// 根据ID获取单个服务
function getServiceById(serviceId) {
  return allServices.find(s => String(s.id) === String(serviceId)) || null
}

// 搜索服务
function searchServices(keyword) {
  if (!keyword) return []
  const kw = keyword.toLowerCase()
  return allServices.filter(s =>
    s.name.toLowerCase().includes(kw) ||
    s.desc.toLowerCase().includes(kw) ||
    s.tag.toLowerCase().includes(kw)
  )
}

// 获取首页标签格式的数据（带services数组）
// 用分类列表动态生成，每个分类对应一个"火热标签"
function getHotTagsWithServices() {
  return categories.map(cat => ({
    name: cat.name,
    categoryId: cat.id,
    services: getServicesByCategory(cat.id)
  }))
}

// 获取分类页格式的数据（每个分类带services数组）
function getCategoriesWithServices() {
  return categories.map(cat => ({
    ...cat,
    services: getServicesByCategory(cat.id)
  }))
}

module.exports = {
  allServices,
  categories,
  tagColors,
  loadServicesFromServer,
  loadCategoriesFromServer,
  loadBannersFromServer,
  loadAllFromServer,
  getServicesByCategory,
  getServiceById,
  searchServices,
  getHotTagsWithServices,
  getCategoriesWithServices
}
