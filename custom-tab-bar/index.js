// custom-tab-bar/index.js
Component({
  data: {
    selected: 0,
    list: [
      {
        pagePath: '/pages/index/index',
        text: '首页',
        icon: '/images/tab_home.png',
        activeIcon: '/images/tab_home_active.png'
      },
      {
        pagePath: '/pages/message/message',
        text: '分类',
        icon: '/images/tab_msg.png',
        activeIcon: '/images/tab_msg_active.png'
      },
      {
        // 占位，下单按钮在中间凸起
        pagePath: '',
        text: '下单',
        icon: '',
        activeIcon: ''
      },
      {
        pagePath: '/pages/join/join',
        text: '成为护航',
        icon: '/images/tab_join.png',
        activeIcon: '/images/tab_join_active.png'
      },
      {
        pagePath: '/pages/mine/mine',
        text: '我的',
        icon: '/images/tab_mine.png',
        activeIcon: '/images/tab_mine_active.png'
      }
    ]
  },
  methods: {
    switchTab(e) {
      const idx = e.currentTarget.dataset.index
      const path = this.data.list[idx].pagePath
      wx.switchTab({ url: path })
    },
    goOrder() {
      wx.navigateTo({
        url: '/pages/orders/orders'
      })
    }
  }
})