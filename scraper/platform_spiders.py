# -*- coding: utf-8 -*-
"""
平台级爬虫：NCSS（国家大学生就业服务平台）、牛客网校招日历、就业在线
"""

import re
import time
import requests
from datetime import datetime

from scraper.config import INDUSTRY_KEYWORDS

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}


# ============================================================
# 通用辅助函数
# ============================================================

def _job_exists(db, company, position):
    """检查同一公司+同一职位是否已存在，避免重复录入"""
    row = db.execute(
        'SELECT 1 FROM jobs WHERE company = ? AND position = ? LIMIT 1',
        (company, position)
    ).fetchone()
    return row is not None


def _insert_job(db, job_data):
    """向 jobs 表插入一条职位记录，返回新记录 id"""
    cursor = db.execute("""
        INSERT INTO jobs (company, position, city, salary, status, deadline,
                         link, notes, priority, source, industry, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_data.get('company', ''),
        job_data.get('position', ''),
        job_data.get('city', ''),
        job_data.get('salary', ''),
        '未投',
        job_data.get('deadline', ''),
        job_data.get('link', ''),
        job_data.get('notes', ''),
        3,
        job_data.get('source', 'scraper'),
        job_data.get('industry', ''),
        datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ))
    db.commit()
    return cursor.lastrowid


def _classify_industry(text, keywords=None):
    """通用行业分类函数，基于关键词匹配。"""
    if keywords is None:
        keywords = INDUSTRY_KEYWORDS
    text = text.lower()
    for industry, words in keywords.items():
        for word in words:
            if word.lower() in text:
                return industry
    return ''


def _classify_niuke_industry(text):
    """牛客网专用行业分类函数，使用更精确的关键词集合。"""
    FINANCE_KW = [
        '银行', '证券', '保险', '基金', '信托', '投行',
        '期货', '资产管理', '财富管理', '金融',
    ]
    INTERNET_KW = [
        '科技', '技术', '互联网', '软件', '信息技术', '数据', '智能',
        '电子', '通信', '半导体', '芯片', '计算机', '网络', '游戏',
        '电商', '算法',
        '字节', '腾讯', '阿里', '百度', '美团', '京东', '网易',
        '滴滴', '快手', 'bilibili', '小红书', '拼多多',
        '华为', '小米', 'oppo', 'vivo',
    ]
    SOE_KW = [
        '中国', '国家', '国有',
        '中铁', '中建', '中交', '中船', '中核',
        '航天', '航空', '兵器',
        '石油', '石化', '电力', '电网', '能源', '烟草', '邮政',
        '电信', '联通', '移动',
        '中化', '中粮', '通用', '国机', '保利', '招商局', '中投',
        '商飞', '中车', '矿冶', '航空工业',
    ]

    text_lower = text.lower()

    for word in FINANCE_KW:
        if word.lower() in text_lower:
            return '金融'
    for word in INTERNET_KW:
        if word.lower() in text_lower:
            return '互联网'
    for word in SOE_KW:
        if word.lower() in text_lower:
            return '国央企'

    return ''


# ============================================================
# NCSS 爬虫 —— 国家大学生就业服务平台
# ============================================================

def scrape_ncss(db, industries, max_pages=5):
    """爬取国家大学生就业服务平台 (NCSS) 职位列表。"""
    api_url = 'https://www.ncss.cn/student/jobs/jobslist/ajax/'
    added = 0

    for page in range(max_pages):
        params = {
            'jobType': '01',
            'offset': page,
            'limit': 20,
            'sourcesName': '0',
        }
        print('[NCSS] 正在爬取第 {0}/{1} 页...'.format(page + 1, max_pages))

        try:
            resp = requests.get(api_url, params=params, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print('[NCSS] 第 {0} 页请求失败: {1}'.format(page + 1, e))
            break

        job_list = data.get('data', {}).get('list', [])
        if not job_list:
            print('[NCSS] 第 {0} 页无数据，停止翻页'.format(page + 1))
            break

        for item in job_list:
            try:
                company = item.get('recName', '').strip()
                position = item.get('jobName', '').strip()

                if not company or not position:
                    continue

                if _job_exists(db, company, position):
                    continue

                low_pay = item.get('lowMonthPay', 0) or 0
                high_pay = item.get('highMonthPay', 0) or 0
                if low_pay and high_pay:
                    salary = '{0}-{1}元/月'.format(int(low_pay * 1000), int(high_pay * 1000))
                elif high_pay:
                    salary = '最高{0}元/月'.format(int(high_pay * 1000))
                elif low_pay:
                    salary = '最低{0}元/月'.format(int(low_pay * 1000))
                else:
                    salary = '面议'

                city = item.get('areaCodeName', '').strip()

                pub_ts = item.get('publishDate', 0) or 0
                if pub_ts and pub_ts > 0:
                    if pub_ts > 1e12:
                        pub_ts = pub_ts / 1000
                    pub_date = datetime.fromtimestamp(pub_ts).strftime('%Y-%m-%d')
                else:
                    pub_date = ''

                degree = item.get('degreeName', '').strip()
                company_type = item.get('recProperty', '').strip()
                company_scale = item.get('recScale', '').strip()

                job_id = item.get('jobId', '')
                link = 'https://www.ncss.cn/student/jobs/{0}/detail.html'.format(job_id) if job_id else ''

                full_text = '{0} {1} {2} {3}'.format(company, position, company_type, company_scale)
                industry = _classify_industry(full_text)

                if industries and industry not in industries:
                    continue

                notes_parts = ['来源：国家大学生就业服务平台']
                if degree:
                    notes_parts.append('学历：{0}'.format(degree))
                if company_type:
                    notes_parts.append('性质：{0}'.format(company_type))
                if company_scale:
                    notes_parts.append('规模：{0}'.format(company_scale))
                notes = ' | '.join(notes_parts)

                _insert_job(db, {
                    'company': company,
                    'position': position,
                    'city': city,
                    'salary': salary,
                    'deadline': pub_date,
                    'link': link,
                    'notes': notes,
                    'source': 'ncss',
                    'industry': industry,
                })
                added += 1

            except Exception as e:
                print('[NCSS] 解析单项失败: {0}'.format(e))
                continue

        if page < max_pages - 1:
            time.sleep(1)

    print('[NCSS] 爬取完成，共新增 {0} 条'.format(added))
    return added


# ============================================================
# 牛客网爬虫 —— 校招日历
# ============================================================

def scrape_niuke(db, industries):
    """爬取牛客网校招日历页面。优先使用 Playwright，失败则回退到 requests。"""
    try:
        from playwright.sync_api import sync_playwright
        return _scrape_niuke_playwright(db, industries)
    except ImportError:
        print('[NIUKE] playwright 未安装，回退到 requests 方式')
        return _scrape_niuke_requests(db, industries)
    except Exception as e:
        print('[NIUKE] Playwright 爬取失败: {0}，回退到 requests 方式'.format(e))
        return _scrape_niuke_requests(db, industries)


def _scrape_niuke_playwright(db, industries):
    """使用 Playwright headless Chromium 爬取牛客网校招日历。"""
    from playwright.sync_api import sync_playwright

    url = 'https://www.nowcoder.com/school/schedule'
    desktop_ua = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )

    print('[NIUKE-PW] Playwright 爬虫启动: {0}'.format(url))

    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=desktop_ua)

            page.goto(url, timeout=30000)
            page.wait_for_selector(
                'a.tw-block.clearfix[href*="enterprise"]',
                timeout=15000
            )

            seen_hrefs = set()
            all_items = []

            for scroll_round in range(5):
                items = page.query_selector_all(
                    'a.tw-block.clearfix[href*="enterprise"]'
                )
                new_count = 0
                for item in items:
                    href = item.get_attribute('href') or ''
                    if href not in seen_hrefs:
                        seen_hrefs.add(href)
                        all_items.append(item)
                        new_count += 1

                print('[NIUKE-PW] 第 {0} 轮滚动: 发现 {1} 条，新增 {2} 条'.format(
                    scroll_round + 1, len(items), new_count
                ))

                if new_count == 0:
                    break

                page.evaluate('window.scrollBy(0, 2000)')
                time.sleep(1.5)

            print('[NIUKE-PW] 共采集 {0} 条记录，开始解析入库'.format(len(all_items)))

            rec_type_pattern = re.compile(
                r'(届|秋招|春招|提前批|暑期)'
            )
            exclude_pattern = re.compile(r'(收录|丨)')

            added = 0
            for item in all_items:
                try:
                    title_el = item.query_selector('.title')
                    if not title_el:
                        continue
                    line_els = title_el.query_selector_all('.line')
                    name_parts = []
                    for le in line_els:
                        t = le.text_content() or ''
                        t = t.strip()
                        if t:
                            name_parts.append(t)
                    company = ' '.join(name_parts) if name_parts else ''
                    if not company:
                        continue

                    city_el = item.query_selector('.city-hidden')
                    cities = city_el.text_content() or '' if city_el else ''
                    cities = cities.strip().strip(',')

                    all_spans = item.query_selector_all('span')
                    rec_types = []
                    collection_date = ''
                    for sp in all_spans:
                        sp_text = sp.text_content() or ''
                        sp_text = sp_text.strip()
                        if not sp_text:
                            continue
                        if '收录' in sp_text:
                            collection_date = sp_text
                        elif rec_type_pattern.search(sp_text) and not exclude_pattern.search(sp_text):
                            rec_types.append(sp_text)

                    rec_type_str = ' '.join(rec_types) if rec_types else ''

                    href = item.get_attribute('href') or ''
                    if href.startswith('/'):
                        link = 'https://www.nowcoder.com' + href
                    else:
                        link = href

                    deliver_el = item.query_selector('.deliver-btn')
                    deliver_method = deliver_el.text_content() or '' if deliver_el else ''
                    deliver_method = deliver_method.strip()

                    position = rec_type_str if rec_type_str else '校园招聘'

                    if _job_exists(db, company, position):
                        continue

                    industry = _classify_niuke_industry(company)
                    if industries and industry not in industries:
                        continue

                    notes_parts = ['来源：牛客网校招日历']
                    if rec_type_str:
                        notes_parts.append('类型：{0}'.format(rec_type_str))
                    if collection_date:
                        notes_parts.append('收录：{0}'.format(collection_date))
                    if cities:
                        notes_parts.append('城市：{0}'.format(cities))
                    if deliver_method:
                        notes_parts.append('投递：{0}'.format(deliver_method))
                    notes = ' | '.join(notes_parts)

                    _insert_job(db, {
                        'company': company,
                        'position': position,
                        'city': cities,
                        'salary': '',
                        'deadline': collection_date,
                        'link': link,
                        'notes': notes,
                        'source': 'niuke',
                        'industry': industry,
                    })
                    added += 1

                except Exception as e:
                    print('[NIUKE-PW] 解析单项失败: {0}'.format(e))
                    continue

            print('[NIUKE-PW] Playwright 爬取完成，共新增 {0} 条'.format(added))
            return added

    except Exception as e:
        print('[NIUKE-PW] Playwright 执行异常: {0}'.format(e))
        raise
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass


def _scrape_niuke_requests(db, industries):
    """牛客网 requests+BeautifulSoup 备用爬虫（旧版实现）。"""
    url = 'https://www.nowcoder.com/school/schedule'
    print('[NIUKE-REQ] requests 备用爬虫启动: {0}'.format(url))

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print('[NIUKE-REQ] 请求失败: {0}，尝试移动端备用方案'.format(e))
        return _scrape_niuke_mobile(db, industries)

    resp_text = resp.text
    if 'slide' in resp_text.lower() or len(resp_text) < 5000:
        print('[NIUKE-REQ] 检测到滑块验证或页面异常，切换到移动端备用方案')
        return _scrape_niuke_mobile(db, industries)

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp_text, 'html.parser')

    company_blocks = soup.select('.act-company-body')
    print('[NIUKE-REQ] 解析到 {0} 个公司信息块'.format(len(company_blocks)))

    added = 0
    for block in company_blocks:
        try:
            h2 = block.select_one('h2')
            company = h2.get_text(strip=True) if h2 else ''
            if not company:
                continue

            date_el = block.select_one('.act-company-info .act-company-time')
            date_text = date_el.get_text(strip=True) if date_el else ''

            intro_el = block.select_one('.company-short-introduce')
            intro_text = intro_el.get_text(strip=True) if intro_el else ''

            location_el = block.select_one('.company-content')
            location = location_el.get_text(strip=True) if location_el else ''

            position = '校园招聘'

            if _job_exists(db, company, position):
                continue

            classify_text = '{0} {1} {2}'.format(company, intro_text, location)
            industry = _classify_niuke_industry(classify_text)

            if industries and industry not in industries:
                continue

            notes_parts = ['来源：牛客网校招日历']
            if date_text:
                notes_parts.append('日期：{0}'.format(date_text))
            if location:
                notes_parts.append('地点：{0}'.format(location))
            if intro_text:
                notes_parts.append('简介：{0}'.format(intro_text[:100]))
            notes = ' | '.join(notes_parts)

            link = url

            city = ''
            if location:
                city_match = re.search(r'([一-龥]+(?:市|省|自治区))', location)
                if city_match:
                    city = city_match.group(1)
                else:
                    city = location.split()[0][:10] if location else ''

            _insert_job(db, {
                'company': company,
                'position': position,
                'city': city,
                'salary': '',
                'deadline': date_text,
                'link': link,
                'notes': notes,
                'source': 'niuke',
                'industry': industry,
            })
            added += 1

        except Exception as e:
            print('[NIUKE-REQ] 解析单项失败: {0}'.format(e))
            continue

    if added == 0:
        print('[NIUKE-REQ] 未获取到有效数据，尝试移动端备用方案')
        return _scrape_niuke_mobile(db, industries)

    print('[NIUKE-REQ] 爬取完成，共新增 {0} 条'.format(added))
    return added


# ============================================================
# 牛客网移动端备用爬虫
# ============================================================

def _scrape_niuke_mobile(db, industries):
    """牛客网移动端备用爬虫，优先尝试 Playwright + 移动端 UA，失败则回退 requests。"""
    try:
        from playwright.sync_api import sync_playwright
        return _scrape_niuke_mobile_playwright(db, industries)
    except ImportError:
        print('[NIUKE-M] playwright 未安装，回退到 requests 移动端')
        return _scrape_niuke_mobile_requests(db, industries)
    except Exception as e:
        print('[NIUKE-M] Playwright 移动端失败: {0}，回退到 requests'.format(e))
        return _scrape_niuke_mobile_requests(db, industries)


def _scrape_niuke_mobile_playwright(db, industries):
    """使用 Playwright + 移动端 UA 爬取牛客网校招日历。"""
    from playwright.sync_api import sync_playwright

    url = 'https://m.nowcoder.com/school/schedule'
    mobile_ua = (
        'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) '
        'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 '
        'Mobile/15E148 Safari/604.1'
    )

    print('[NIUKE-M-PW] Playwright 移动端爬虫启动: {0}'.format(url))

    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=mobile_ua)

            page.goto(url, timeout=30000)
            page.wait_for_selector(
                'a.tw-block.clearfix[href*="enterprise"]',
                timeout=15000
            )

            seen_hrefs = set()
            all_items = []

            for scroll_round in range(3):
                items = page.query_selector_all(
                    'a.tw-block.clearfix[href*="enterprise"]'
                )
                new_count = 0
                for item in items:
                    href = item.get_attribute('href') or ''
                    if href not in seen_hrefs:
                        seen_hrefs.add(href)
                        all_items.append(item)
                        new_count += 1

                print('[NIUKE-M-PW] 第 {0} 轮: 新增 {1} 条'.format(
                    scroll_round + 1, new_count
                ))

                if new_count == 0:
                    break

                page.evaluate('window.scrollBy(0, 2000)')
                time.sleep(1.5)

            print('[NIUKE-M-PW] 共采集 {0} 条，开始解析'.format(len(all_items)))

            rec_type_pattern = re.compile(r'(届|秋招|春招|提前批|暑期)')
            exclude_pattern = re.compile(r'(收录|丨)')

            added = 0
            for item in all_items:
                try:
                    title_el = item.query_selector('.title')
                    if not title_el:
                        continue
                    line_els = title_el.query_selector_all('.line')
                    name_parts = []
                    for le in line_els:
                        t = le.text_content() or ''
                        t = t.strip()
                        if t:
                            name_parts.append(t)
                    company = ' '.join(name_parts) if name_parts else ''
                    if not company:
                        continue

                    city_el = item.query_selector('.city-hidden')
                    cities = city_el.text_content() or '' if city_el else ''
                    cities = cities.strip().strip(',')

                    all_spans = item.query_selector_all('span')
                    rec_types = []
                    collection_date = ''
                    for sp in all_spans:
                        sp_text = sp.text_content() or ''
                        sp_text = sp_text.strip()
                        if not sp_text:
                            continue
                        if '收录' in sp_text:
                            collection_date = sp_text
                        elif rec_type_pattern.search(sp_text) and not exclude_pattern.search(sp_text):
                            rec_types.append(sp_text)

                    rec_type_str = ' '.join(rec_types) if rec_types else ''
                    href = item.get_attribute('href') or ''
                    if href.startswith('/'):
                        link = 'https://www.nowcoder.com' + href
                    else:
                        link = href

                    deliver_el = item.query_selector('.deliver-btn')
                    deliver_method = deliver_el.text_content() or '' if deliver_el else ''
                    deliver_method = deliver_method.strip()

                    position = rec_type_str if rec_type_str else '校园招聘'

                    if _job_exists(db, company, position):
                        continue

                    industry = _classify_niuke_industry(company)
                    if industries and industry not in industries:
                        continue

                    notes_parts = ['来源：牛客网校招日历(移动端)']
                    if rec_type_str:
                        notes_parts.append('类型：{0}'.format(rec_type_str))
                    if collection_date:
                        notes_parts.append('收录：{0}'.format(collection_date))
                    if cities:
                        notes_parts.append('城市：{0}'.format(cities))
                    if deliver_method:
                        notes_parts.append('投递：{0}'.format(deliver_method))
                    notes = ' | '.join(notes_parts)

                    _insert_job(db, {
                        'company': company,
                        'position': position,
                        'city': cities,
                        'salary': '',
                        'deadline': collection_date,
                        'link': link,
                        'notes': notes,
                        'source': 'niuke',
                        'industry': industry,
                    })
                    added += 1

                except Exception as e:
                    print('[NIUKE-M-PW] 解析单项失败: {0}'.format(e))
                    continue

            print('[NIUKE-M-PW] 移动端爬取完成，共新增 {0} 条'.format(added))
            return added

    except Exception as e:
        print('[NIUKE-M-PW] Playwright 移动端异常: {0}'.format(e))
        raise
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass


def _scrape_niuke_mobile_requests(db, industries):
    """牛客网移动端 requests 备用爬虫。"""
    mobile_headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) '
                      'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 '
                      'Mobile/15E148 Safari/604.1',
    }
    url = 'https://m.nowcoder.com/school/schedule'
    print('[NIUKE-M-REQ] requests 移动端备用爬虫启动: {0}'.format(url))

    try:
        resp = requests.get(url, headers=mobile_headers, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print('[NIUKE-M-REQ] 移动端请求失败: {0}'.format(e))
        return 0

    if 'slide' in resp.text.lower() or len(resp.text) < 5000:
        print('[NIUKE-M-REQ] 移动端仍被验证码拦截，本次爬取终止')
        return 0

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, 'html.parser')

    items = soup.select('.act-company-body')
    if not items:
        items = soup.select('.company-item, .schedule-item, .recruit-item')

    if not items:
        print('[NIUKE-M-REQ] 移动端页面未找到有效数据块')
        return 0

    print('[NIUKE-M-REQ] 解析到 {0} 个信息块'.format(len(items)))

    added = 0
    for item in items:
        try:
            h2 = item.select_one('h2, h3, .company-name, .name')
            company = h2.get_text(strip=True) if h2 else ''
            if not company:
                a_tag = item.find('a')
                if a_tag:
                    company = a_tag.get_text(strip=True)
            if not company:
                continue

            position = '校园招聘'

            if _job_exists(db, company, position):
                continue

            date_el = item.select_one('.act-company-time, .time, .date')
            date_text = date_el.get_text(strip=True) if date_el else ''

            loc_el = item.select_one('.company-content, .location, .city')
            location = loc_el.get_text(strip=True) if loc_el else ''

            intro_el = item.select_one('.company-short-introduce, .intro, .desc')
            intro_text = intro_el.get_text(strip=True) if intro_el else ''

            classify_text = '{0} {1} {2}'.format(company, intro_text, location)
            industry = _classify_niuke_industry(classify_text)

            if industries and industry not in industries:
                continue

            notes_parts = ['来源：牛客网校招日历(移动端)']
            if date_text:
                notes_parts.append('日期：{0}'.format(date_text))
            if location:
                notes_parts.append('地点：{0}'.format(location))
            if intro_text:
                notes_parts.append('简介：{0}'.format(intro_text[:100]))
            notes = ' | '.join(notes_parts)

            city = ''
            if location:
                city_match = re.search(r'([一-龥]+(?:市|省|自治区))', location)
                if city_match:
                    city = city_match.group(1)

            _insert_job(db, {
                'company': company,
                'position': position,
                'city': city,
                'salary': '',
                'deadline': date_text,
                'link': url,
                'notes': notes,
                'source': 'niuke',
                'industry': industry,
            })
            added += 1

        except Exception as e:
            print('[NIUKE-M-REQ] 解析单项失败: {0}'.format(e))
            continue

    print('[NIUKE-M-REQ] 移动端爬取完成，共新增 {0} 条'.format(added))
    return added


# ============================================================
# 就业在线爬虫（已放弃）
# ============================================================

def scrape_jobonline(db, industries):
    """
    就业在线 (jobonline.cn) 爬虫 -- 已放弃。

    原因：该网站登录及数据传输采用 SM2/SM4 国密加密体系，
    前端所有请求参数和响应数据均经过加密处理，无法通过常规
    HTTP 请求方式获取明文职位数据。

    如需获取该平台数据，建议：
    1. 使用 Selenium/Playwright 模拟真实浏览器操作
    2. 逆向分析其加密 JS 模块，还原加解密逻辑
    3. 通过官方合作渠道获取数据接口
    """
    print('[JOBONLINE] 就业在线(jobonline.cn)爬取已放弃')
    print('[JOBONLINE] 原因：该网站使用 SM2/SM4 国密加密，无法直接解析数据')
    print('[JOBONLINE] 建议：使用 Selenium 模拟浏览器，或逆向分析加密模块')
    return 0
