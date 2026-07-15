# 秋招信息追踪平台

一个用于跟踪秋季校园招聘信息的 Web 应用，支持自动爬取多个平台的招聘数据。

## 功能特性

- 职位管理：添加、编辑、删除、筛选招聘信息
- 投递跟踪：未投→已投→笔试→面试→OC/拒 全流程追踪
- 自动爬取：支持多个数据源的自动抓取
- 数据导出：CSV 格式导出
- 密码保护：共享密码访问

## 支持的数据源

| 数据源 | 类型 | 状态 |
|--------|------|------|
| 国家大学生就业服务平台 (NCSS) | 公开API | 可用 |
| 牛客网校招日历 | Playwright自动化 | 可用 |
| 就业在线 | - | 加密暂不可用 |
| 西南财经大学就业网 | HTML解析 | 可用 |
| 四川大学就业网 | HTML解析 | 可用 |
| 兰州大学就业网 | HTML解析 | 可用 |

## 技术栈

- 后端: Python Flask + SQLite
- 前端: 纯 HTML/CSS/JavaScript
- 爬虫: requests + BeautifulSoup + Playwright

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 启动应用

```bash
python app.py
```

默认密码: `qiuzhao2026`
访问地址: http://127.0.0.1:5000

## 部署 (Render)

1. 在 GitHub 创建仓库并推送代码
2. 在 Render 创建 Web Service
3. 连接 GitHub 仓库
4. Build Command: `pip install -r requirements.txt && playwright install chromium --with-deps`
5. Start Command: `gunicorn app:app` 或 `python app.py`
6. 环境变量 `APP_PASSWORD` 设置自定义密码

## 项目结构

```
job_tracker/
├── app.py                  # Flask 主应用
├── scraper/
│   ├── config.py           # 爬虫数据源配置
│   ├── platform_spiders.py # 平台爬虫 (NCSS/牛客/就业在线)
│   └── university_spiders.py # 高校爬虫 (985/211)
├── static/
│   ├── script.js           # 前端逻辑
│   └── style.css           # 样式表
├── templates/
│   ├── index.html          # 主页面
│   └── login.html          # 登录页面
├── requirements.txt        # Python 依赖
└── database.db             # SQLite 数据库 (自动创建)
```

## 扩展数据源

在 `scraper/config.py` 的 `UNIVERSITY_SOURCES` 中添加新的高校配置，
然后在 `scraper/university_spiders.py` 中编写对应的解析函数。

## 许可证

MIT
