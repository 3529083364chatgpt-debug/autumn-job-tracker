import sqlite3
import os
import csv
import json
import io
import threading
import time
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, jsonify, g, session, redirect, url_for, Response
from scraper.config import SOURCES, UNIVERSITY_SOURCES

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ======== 密码保护配置 ========
# 可通过环境变量设置密码，默认密码为 qiuzhao2026
APP_PASSWORD = os.environ.get('APP_PASSWORD', 'qiuzhao2026')

DATABASE = os.path.join(os.path.dirname(__file__), 'database.db')

# ======== 爬虫异步状态 ========
_scrape_status = {
    'running': False,
    'results': [],
    'started_at': '',
}

# ======== 数据库操作 ========

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

@app.before_request
def ensure_db():
    if not os.path.exists(DATABASE):
        init_db()
    else:
        with app.app_context():
            db = get_db()
            try:
                db.execute('SELECT 1 FROM jobs LIMIT 1')
            except sqlite3.OperationalError:
                init_db()

def init_db():
    with app.app_context():
        db = get_db()
        db.executescript('''
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                position TEXT NOT NULL,
                city TEXT,
                salary TEXT,
                status TEXT DEFAULT '未投',
                deadline TEXT,
                link TEXT,
                notes TEXT,
                priority INTEGER DEFAULT 3,
                source TEXT DEFAULT 'manual',
                industry TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_deadline ON jobs(deadline);
            CREATE INDEX IF NOT EXISTS idx_source ON jobs(source);
            CREATE INDEX IF NOT EXISTS idx_industry ON jobs(industry);
        ''')
        db.commit()

# ======== 登录验证装饰器 ========

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            if request.is_json:
                return jsonify({'error': '未登录'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# ======== 页面路由 ========

@app.route('/login', methods=['GET'])
def login_page():
    if session.get('logged_in'):
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    password = data.get('password', '')
    if password == APP_PASSWORD:
        session['logged_in'] = True
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': '密码错误'}), 401

@app.route('/api/logout', methods=['POST'])
@login_required
def api_logout():
    session.pop('logged_in', None)
    return jsonify({'success': True})

@app.route('/')
@login_required
def index():
    return render_template('index.html')

# ======== API 路由 ========

@app.route('/api/jobs', methods=['GET'])
@login_required
def get_jobs():
    db = get_db()
    status = request.args.get('status', '')
    city = request.args.get('city', '')
    keyword = request.args.get('keyword', '')
    industry = request.args.get('industry', '')
    source = request.args.get('source', '')
    sort_by = request.args.get('sort_by', 'created_at')
    sort_order = request.args.get('sort_order', 'DESC')

    query = 'SELECT * FROM jobs WHERE 1=1'
    params = []

    if status:
        query += ' AND status = ?'
        params.append(status)
    if city:
        query += ' AND city LIKE ?'
        params.append(f'%{city}%')
    if keyword:
        query += ' AND (company LIKE ? OR position LIKE ? OR notes LIKE ?)'
        params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])
    if industry:
        query += ' AND industry = ?'
        params.append(industry)
    if source:
        query += ' AND source = ?'
        params.append(source)

    allowed_sort = ['created_at', 'deadline', 'priority', 'company']
    if sort_by in allowed_sort:
        query += f' ORDER BY {sort_by}'
        query += ' ASC' if sort_order.upper() == 'ASC' else ' DESC'

    jobs = db.execute(query, params).fetchall()
    return jsonify([dict(job) for job in jobs])

@app.route('/api/jobs', methods=['POST'])
@login_required
def add_job():
    data = request.get_json()
    db = get_db()
    cursor = db.execute('''
        INSERT INTO jobs (company, position, city, salary, status, deadline, link, notes, priority, source, industry)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('company', ''),
        data.get('position', ''),
        data.get('city', ''),
        data.get('salary', ''),
        data.get('status', '未投'),
        data.get('deadline', ''),
        data.get('link', ''),
        data.get('notes', ''),
        data.get('priority', 3),
        data.get('source', 'manual'),
        data.get('industry', '')
    ))
    db.commit()
    job_id = cursor.lastrowid
    job = db.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
    return jsonify(dict(job)), 201

@app.route('/api/jobs/<int:job_id>', methods=['PUT'])
@login_required
def update_job(job_id):
    data = request.get_json()
    db = get_db()
    job = db.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
    if not job:
        return jsonify({'error': '记录不存在'}), 404

    db.execute('''
        UPDATE jobs
        SET company = ?, position = ?, city = ?, salary = ?, status = ?,
            deadline = ?, link = ?, notes = ?, priority = ?, industry = ?
        WHERE id = ?
    ''', (
        data.get('company', job['company']),
        data.get('position', job['position']),
        data.get('city', job['city']),
        data.get('salary', job['salary']),
        data.get('status', job['status']),
        data.get('deadline', job['deadline']),
        data.get('link', job['link']),
        data.get('notes', job['notes']),
        data.get('priority', job['priority']),
        data.get('industry', job['industry']),
        job_id
    ))
    db.commit()
    job = db.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
    return jsonify(dict(job))

@app.route('/api/jobs/<int:job_id>', methods=['DELETE'])
@login_required
def delete_job(job_id):
    db = get_db()
    job = db.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
    if not job:
        return jsonify({'error': '记录不存在'}), 404
    db.execute('DELETE FROM jobs WHERE id = ?', (job_id,))
    db.commit()
    return jsonify({'message': '删除成功'})

@app.route('/api/jobs/<int:job_id>', methods=['GET'])
@login_required
def get_job(job_id):
    db = get_db()
    job = db.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
    if not job:
        return jsonify({'error': '记录不存在'}), 404
    return jsonify(dict(job))

@app.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    db = get_db()
    total = db.execute('SELECT COUNT(*) as count FROM jobs').fetchone()['count']
    status_counts = db.execute('SELECT status, COUNT(*) as count FROM jobs GROUP BY status').fetchall()
    industry_counts = db.execute('SELECT industry, COUNT(*) as count FROM jobs WHERE industry IS NOT NULL AND industry != "" GROUP BY industry').fetchall()
    seven_days_later = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')
    urgent = db.execute('''
        SELECT COUNT(*) as count FROM jobs
        WHERE deadline <= ? AND deadline >= ? AND status IN ('未投', '已投')
    ''', (seven_days_later, today)).fetchone()['count']
    return jsonify({
        'total': total,
        'status_counts': {row['status']: row['count'] for row in status_counts},
        'industry_counts': {row['industry']: row['count'] for row in industry_counts},
        'urgent': urgent
    })

@app.route('/api/cities', methods=['GET'])
@login_required
def get_cities():
    db = get_db()
    cities = db.execute('SELECT DISTINCT city FROM jobs WHERE city IS NOT NULL AND city != ""').fetchall()
    return jsonify([row['city'] for row in cities])

@app.route('/api/export', methods=['GET'])
@login_required
def export_csv():
    db = get_db()
    status = request.args.get('status', '')
    city = request.args.get('city', '')
    keyword = request.args.get('keyword', '')
    industry = request.args.get('industry', '')

    query = 'SELECT * FROM jobs WHERE 1=1'
    params = []
    if status:
        query += ' AND status = ?'; params.append(status)
    if city:
        query += ' AND city LIKE ?'; params.append(f'%{city}%')
    if keyword:
        query += ' AND (company LIKE ? OR position LIKE ? OR notes LIKE ?)'
        params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])
    if industry:
        query += ' AND industry = ?'; params.append(industry)

    jobs = db.execute(query, params).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['公司', '岗位', '城市', '薪资', '状态', '截止日期', '投递链接', '优先级', '行业', '来源', '备注/面经'])
    for job in jobs:
        writer.writerow([
            job['company'], job['position'], job['city'] or '', job['salary'] or '',
            job['status'], job['deadline'] or '', job['link'] or '', job['priority'],
            job['industry'] or '', job['source'] or 'manual', job['notes'] or ''
        ])

    response = Response(output.getvalue(), mimetype='text/csv; charset=utf-8-sig')
    response.headers['Content-Disposition'] = 'attachment; filename=jobs_export.csv'
    return response

@app.route('/api/scraper/run', methods=['POST'])
@login_required
def run_scraper():
    """启动后台爬虫任务"""
    global _scrape_status
    if _scrape_status['running']:
        return jsonify({'message': '爬虫正在运行中，请稍候', 'status': 'running'})

    data = request.get_json() or {}
    sources = data.get('sources', ['ncss'])
    industries = data.get('industries', ['金融', '互联网', '国央企'])

    # If sources is ['all'], use all available
    if sources == ['all'] or sources == 'all':
        sources = ['ncss']
        for uni_key, config in UNIVERSITY_SOURCES.items():
            if config.get('enabled') and config.get('url'):
                sources.append(uni_key)

    _scrape_status = {
        'running': True,
        'results': [],
        'started_at': datetime.now().strftime('%H:%M:%S'),
    }

    thread = threading.Thread(target=_run_scraper_bg, args=(sources, industries))
    thread.daemon = True
    thread.start()

    return jsonify({'message': '开始抓取...', 'status': 'started', 'sources': sources})

def _run_scraper_bg(sources, industries):
    """后台线程执行爬虫"""
    global _scrape_status
    db_path = DATABASE
    for source_name in sources:
        try:
            db = sqlite3.connect(db_path)
            count = scrape_source(source_name, industries, db)
            db.close()
            _scrape_status['results'].append({
                'source': source_name, 'added': count, 'status': 'success'
            })
        except Exception as e:
            err_msg = str(e)
            if 'timeout' in err_msg.lower() or 'connection' in err_msg.lower():
                err_msg = '网络超时：目标网站可能屏蔽了海外IP'
            elif '403' in err_msg or 'forbidden' in err_msg.lower():
                err_msg = '访问被拒绝：目标网站屏蔽了当前IP'
            elif '404' in err_msg:
                err_msg = '页面不存在：链接可能已过期'
            _scrape_status['results'].append({
                'source': source_name, 'added': 0, 'status': 'error', 'message': err_msg
            })
    _scrape_status['running'] = False

@app.route('/api/scraper/status', methods=['GET'])
@login_required
def get_scraper_status():
    """查询爬虫进度"""
    return jsonify(_scrape_status)


@app.route('/api/jobs/import', methods=['POST'])
@login_required
def import_jobs():
    """导入JSON格式的职位数据"""
    if 'file' not in request.files:
        return jsonify({'error': '请选择文件'}), 400

    file = request.files['file']
    if not file.filename.endswith('.json'):
        return jsonify({'error': '仅支持JSON文件'}), 400

    try:
        data = json.load(file)
    except:
        return jsonify({'error': 'JSON格式错误'}), 400

    jobs = data.get('jobs', [])
    if not jobs:
        return jsonify({'error': '文件中没有职位数据'}), 400

    db = get_db()
    added = 0
    for job in jobs:
        company = job.get('company', '').strip()
        position = job.get('position', '').strip()
        if not company or not position:
            continue

        # Dedup
        existing = db.execute('SELECT 1 FROM jobs WHERE company = ? AND position = ? LIMIT 1', (company, position)).fetchone()
        if existing:
            continue

        db.execute('''
            INSERT INTO jobs (company, position, city, salary, status, deadline, link, notes, priority, source, industry, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            company,
            position,
            job.get('city', ''),
            job.get('salary', ''),
            job.get('status', '未投'),
            job.get('deadline', ''),
            job.get('link', ''),
            job.get('notes', ''),
            job.get('priority', 3),
            job.get('source', 'import'),
            job.get('industry', ''),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))
        added += 1

    db.commit()
    return jsonify({'success': True, 'added': added, 'total': len(jobs), 'skipped': len(jobs) - added})


@app.route('/api/jobs/export', methods=['GET'])
@login_required
def export_jobs():
    """导出所有职位为JSON"""
    db = get_db()
    rows = db.execute('SELECT company, position, city, salary, status, deadline, link, notes, priority, source, industry FROM jobs').fetchall()
    jobs = []
    for row in rows:
        jobs.append({
            'company': row[0], 'position': row[1], 'city': row[2],
            'salary': row[3], 'status': row[4], 'deadline': row[5],
            'link': row[6], 'notes': row[7], 'priority': row[8],
            'source': row[9], 'industry': row[10],
        })
    output = {'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'total': len(jobs), 'jobs': jobs}
    resp = jsonify(output)
    resp.headers['Content-Disposition'] = 'attachment; filename=jobs_export.json'
    return resp

# ======== 爬虫模块（占位，后续扩展）========

def scrape_source(source_name, industries, db=None):
    """
    爬虫入口函数。
    source_name: 'niuke' | 'ncss' | 'jobonline' | 'uni_xxx'
    industries: ['金融', '互联网', '国央企']
    db: SQLite 数据库连接
    返回：新增记录数
    """
    if db is None:
        print('[爬虫] 缺少数据库连接，无法执行爬取')
        return 0

    if source_name == 'niuke':
        from scraper.platform_spiders import scrape_niuke
        return scrape_niuke(db, industries)
    elif source_name == 'ncss':
        from scraper.platform_spiders import scrape_ncss
        return scrape_ncss(db, industries)
    elif source_name == 'jobonline':
        from scraper.platform_spiders import scrape_jobonline
        return scrape_jobonline(db, industries)
    elif source_name == 'yjszp':
        from scraper.platform_spiders import scrape_yjszp
        return scrape_yjszp(db, industries)
    elif source_name.startswith('uni_'):
        return scrape_university(source_name, industries, db)
    else:
        return 0

def scrape_university(uni_key, industries, db=None):
    """
    爬取指定大学就业信息网
    uni_key: 如 'uni_pku', 'uni_thu', 'uni_swufe' 等
    industries: ['金融', '互联网', '国央企']
    db: SQLite 数据库连接
    返回：新增记录数
    """
    config = UNIVERSITY_SOURCES.get(uni_key)
    if not config:
        print(f'[爬虫] 未知数据源: {uni_key}')
        return 0
    if not config.get('enabled'):
        print(f'[爬虫] 数据源未启用: {config["name"]}')
        return 0
    if not config.get('url') and not config.get('list_url'):
        print(f'[爬虫] 数据源 URL 未配置: {config["name"]}')
        return 0
    if db is None:
        print(f'[爬虫] 缺少数据库连接，无法爬取大学数据源')
        return 0

    print(f'[爬虫] 正在爬取 {config["name"]}...')

    if uni_key == 'uni_swufe':
        from scraper.university_spiders import scrape_swufe
        return scrape_swufe(db, industries, config)
    elif uni_key == 'uni_scu':
        from scraper.university_spiders import scrape_scu
        return scrape_scu(db, industries, config)
    elif uni_key == 'uni_lzu':
        from scraper.university_spiders import scrape_lzu
        return scrape_lzu(db, industries, config)
    elif uni_key == 'uni_pku':
        from scraper.university_spiders import scrape_wanxiao
        return scrape_wanxiao(db, industries, config, 'pku')
    elif uni_key == 'uni_buaa':
        from scraper.university_spiders import scrape_wanxiao
        return scrape_wanxiao(db, industries, config, 'buaa')
    elif uni_key == 'uni_bit':
        from scraper.university_spiders import scrape_wanxiao
        return scrape_wanxiao(db, industries, config, 'bit')
    elif uni_key in ('uni_sjtu', 'uni_sufe'):
        from scraper.university_spiders import scrape_yijy
        return scrape_yijy(db, industries, config)
    elif uni_key == 'uni_uibe':
        from scraper.university_spiders import scrape_uibe
        return scrape_uibe(db, industries, config)
    elif uni_key == 'uni_sysu':
        from scraper.university_spiders import scrape_sysu
        return scrape_sysu(db, industries, config)

    # 其他学校待实现
    print(f'[爬虫] {config["name"]} 尚未实现具体解析逻辑')
    return 0

# ======== 启动 ========

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        init_db()
    else:
        with app.app_context():
            db = get_db()
            try:
                db.execute('SELECT 1 FROM jobs LIMIT 1')
            except sqlite3.OperationalError:
                init_db()

    print('=' * 50)
    print('  秋招信息追踪平台 启动中...')
    print('  默认密码: qiuzhao2026')
    print('  请在浏览器打开: http://127.0.0.1:5000')
    print('=' * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)
