import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from scraper.config import INDUSTRY_KEYWORDS

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}


def _job_exists(db, company, position):
    row = db.execute(
        'SELECT 1 FROM jobs WHERE company = ? AND position = ? LIMIT 1',
        (company, position)
    ).fetchone()
    return row is not None


def _insert_job(db, job_data):
    cursor = db.execute('''
        INSERT INTO jobs (company, position, city, salary, status, deadline, link, notes, priority, source, industry, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
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
    if keywords is None:
        keywords = INDUSTRY_KEYWORDS
    text = text.lower()
    for industry, words in keywords.items():
        for word in words:
            if word.lower() in text:
                return industry
    return ''


def scrape_swufe(db, industries, config):
    base_url = 'https://job3.swufe.edu.cn'
    list_url = base_url + '/jobs/jobs_list.htm'

    print(f'[SWUFE] 开始爬取: {list_url}')
    try:
        resp = requests.get(list_url, headers=HEADERS, timeout=30)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        print(f'[SWUFE] 请求失败: {e}')
        return 0

    added = 0
    items = soup.select('div.J_jobsList.yli')
    print(f'[SWUFE] 解析到 {len(items)} 个职位项')

    for item in items:
        try:
            name_a = item.select_one('div.td-j-name a')
            position = name_a.get_text(strip=True) if name_a else ''

            salary_span = item.select_one('span.position-salary')
            salary = salary_span.get_text(strip=True) if salary_span else ''

            company_a = item.select_one('div.td3 a.line_substring')
            company = company_a.get_text(strip=True) if company_a else ''

            city = ''
            pub_date = ''
            for span in item.select('div.detail div.txt span'):
                txt = span.get_text(strip=True)
                if txt.startswith('城市：'):
                    city = txt.replace('城市：', '').strip()
                elif txt.startswith('发布时间：'):
                    pub_date = txt.replace('发布时间：', '').strip()

            industry_text = ''
            people_div = item.select_one('div.people')
            if people_div:
                industry_text = people_div.get_text(strip=True)

            link = ''
            if name_a and name_a.get('href'):
                href = name_a['href']
                if href.startswith('http'):
                    link = href
                else:
                    link = base_url + href

            if not company or not position:
                continue

            full_text = f'{company} {position} {industry_text}'
            industry = _classify_industry(full_text)

            if industries and industry not in industries:
                continue

            if _job_exists(db, company, position):
                continue

            _insert_job(db, {
                'company': company,
                'position': position,
                'city': city,
                'salary': salary,
                'deadline': pub_date,
                'link': link,
                'notes': f'来源：{config["name"]} | 行业/规模：{industry_text}',
                'source': 'scraper',
                'industry': industry,
            })
            added += 1

        except Exception as e:
            print(f'[SWUFE] 解析单项失败: {e}')
            continue

    print(f'[SWUFE] 爬取完成，新增 {added} 条')
    return added


def scrape_scu(db, industries, config):
    """
    爬取四川大学就业信息网职位列表
    URL: http://jy.scu.edu.cn/index/index/employjob.html
    """
    base_url = 'http://jy.scu.edu.cn'
    list_url = base_url + '/index/index/employjob.html'

    print(f'[SCU] 开始爬取: {list_url}')
    try:
        resp = requests.get(list_url, headers=HEADERS, timeout=30)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        print(f'[SCU] 请求失败: {e}')
        return 0

    added = 0
    container = soup.select_one('div.asan-list_right') or soup.select_one('div.asan-list_content')
    if not container:
        print('[SCU] 未找到列表容器')
        return 0

    items = container.find_all('li')
    print(f'[SCU] 找到 {len(items)} 个列表项')

    for idx, item in enumerate(items):
        try:
            # 跳过前3个筛选标签（全职/实习/全职+实习）
            if idx < 3:
                continue

            a = item.find('a', href=True)
            if not a:
                continue

            title = a.get_text(strip=True)
            if not title:
                continue

            # 解析职位名和公司名
            # 格式: 职位名【公司名】
            position = title
            company = ''
            match = re.match(r'^(.*?)【(.*?)】$', title)
            if match:
                position = match.group(1).strip()
                company = match.group(2).strip()

            # 日期
            date_span = item.find('span', class_='list1_time')
            pub_date = date_span.get_text(strip=True) if date_span else ''

            # 链接
            href = a['href']
            if href.startswith('http'):
                link = href
            else:
                link = base_url + href

            if not company or not position:
                continue

            # 行业分类
            full_text = f'{company} {position}'
            industry = _classify_industry(full_text)

            if industries and industry not in industries:
                continue

            if _job_exists(db, company, position):
                continue

            _insert_job(db, {
                'company': company,
                'position': position,
                'city': '',
                'salary': '',
                'deadline': pub_date,
                'link': link,
                'notes': f'来源：{config["name"]}',
                'source': 'scraper',
                'industry': industry,
            })
            added += 1

        except Exception as e:
            print(f'[SCU] 解析单项失败: {e}')
            continue

    print(f'[SCU] 爬取完成，新增 {added} 条')
    return added


def scrape_lzu(db, industries, config):
    """
    爬取兰州大学就业信息网招聘信息列表
    URL: https://job.lzu.edu.cn/html/74/article/list/list_1.html
    """
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    base_url = 'https://job.lzu.edu.cn'
    list_url = base_url + '/html/74/article/list/list_1.html'

    print(f'[LZU] 开始爬取: {list_url}')
    try:
        resp = requests.get(list_url, headers=HEADERS, timeout=30, verify=False)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        print(f'[LZU] 请求失败: {e}')
        return 0

    added = 0
    container = soup.select_one('div.lmain_item_con')
    if not container:
        print('[LZU] 未找到列表容器')
        return 0

    items = container.find_all('a', href=True)
    print(f'[LZU] 找到 {len(items)} 个链接')

    for a in items:
        try:
            title = a.get_text(strip=True)
            href = a['href']

            # 过滤导航链接
            if not title or '/article/202' not in href:
                continue

            # 从父元素中提取日期
            parent = a.find_parent()
            pub_date = ''
            if parent:
                for text_node in parent.stripped_strings:
                    if re.match(r'20\d{2}-\d{2}-\d{2}', text_node):
                        pub_date = text_node.strip()
                        break

            # 提取公司名
            # 去除前缀如 【校招】【央企校招】【国企招聘】
            clean_title = re.sub(r'^[【\[](校招|央企校招|国企招聘|实习)[】\]]\s*', '', title)
            company = ''
            position = '校园招聘'
            match = re.match(r'^(.+?)(?:202\d届|校园招聘|社会招聘|招聘|实习|人才)', clean_title)
            if match:
                company = match.group(1).strip()
                company = re.sub(r'[|\s]+$', '', company)
            else:
                #  fallback: 取标题前10个字作为公司名
                company = clean_title[:20]

            # 链接
            if href.startswith('http'):
                link = href
            else:
                link = base_url + href

            if not company:
                continue

            # 行业分类
            full_text = f'{company} {title}'
            industry = _classify_industry(full_text)

            if industries and industry not in industries:
                continue

            if _job_exists(db, company, position):
                # 同一公司同一position已存在，尝试用position+标题区分
                position = clean_title[:50]
                if _job_exists(db, company, position):
                    continue

            _insert_job(db, {
                'company': company,
                'position': position,
                'city': '',
                'salary': '',
                'deadline': pub_date,
                'link': link,
                'notes': f'来源：{config["name"]} | 公告标题：{title}',
                'source': 'scraper',
                'industry': industry,
            })
            added += 1

        except Exception as e:
            print(f'[LZU] 解析单项失败: {e}')
            continue

    print(f'[LZU] 爬取完成，新增 {added} 条')
    return added


# ============================================================
# 以下为一对多通用爬虫（万校17wanxiao平台 + 易就业平台 + 职派平台）
# ============================================================

def scrape_wanxiao(db, industries, config, school_code):
    """
    万校(17wanxiao)平台通用爬虫
    适用于：北京大学、北京航空航天大学、北京理工大学
    列表页URL: {base_url}/frontpage/{school_code}/html/recruitmentinfoList.html?type=1
    """
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    base_url = config['url'].rstrip('/')
    list_url = base_url + f'/frontpage/{school_code}/html/recruitmentinfoList.html?type=1'

    print(f'[{school_code.upper()}] 开始爬取: {list_url}')
    try:
        resp = requests.get(list_url, headers=HEADERS, timeout=30, verify=False)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        print(f'[{school_code.upper()}] 请求失败: {e}')
        return 0

    added = 0
    # 万校平台用JS渲染列表，尝试找API
    # 检查是否有静态列表项
    items = soup.select('div.positionInfoWrap div.singlePosition, li.list_item')
    if not items:
        # 尝试从script中找数据加载方式
        print(f'[{school_code.upper()}] 列表为空，可能是JS动态渲染，暂无法直接爬取')
        return 0

    for item in items:
        try:
            a = item.find('a', href=True)
            if not a:
                continue
            title = a.get_text(strip=True)
            href = a['href']
            link = base_url + href if not href.startswith('http') else href
            # 提取公司名和职位
            company = ''
            position = title
            match = re.match(r'^(.*?)【(.*?)】', title)
            if match:
                position = match.group(1).strip()
                company = match.group(2).strip()
            if not company:
                continue
            industry = _classify_industry(company + ' ' + position)
            if industries and industry not in industries:
                continue
            if _job_exists(db, company, position):
                continue
            _insert_job(db, {
                'company': company, 'position': position, 'city': '', 'salary': '',
                'deadline': '', 'link': link, 'notes': f'来源：{config["name"]}',
                'source': 'scraper', 'industry': industry,
            })
            added += 1
        except Exception as e:
            continue

    print(f'[{school_code.upper()}] 爬取完成，新增 {added} 条')
    return added


def scrape_yijy(db, industries, config):
    """
    易就业平台通用爬虫
    适用于：上海交通大学、上海财经大学
    列表页URL: {base_url}/career/zpxx/zpxx
    这些平台数据通过JS加载，直接请求HTML为空
    """
    base_url = config['url'].rstrip('/')
    list_url = base_url + '/career/zpxx/zpxx'

    print(f'[YiJY] 开始爬取: {list_url}')
    try:
        resp = requests.get(list_url, headers=HEADERS, timeout=30, verify=False)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        print(f'[YiJY] 请求失败: {e}')
        return 0

    items = soup.select('div.zpxxList')
    if not items:
        print(f'[YiJY] 列表为空，数据通过JS动态渲染，暂无法直接爬取')
        return 0

    added = 0
    for item in items:
        try:
            icon_div = item.select_one('div.zpxxUnitIcon')
            nature_div = item.select_one('div.zpxxUnitNature')
            industry_div = item.select_one('div.zpxxUnitIndustry')
            address_div = item.select_one('div.zpxxUnitAddress')
            time_div = item.select_one('div.zpxxUnitTime')

            company = icon_div.get_text(strip=True) if icon_div else ''
            position = nature_div.get_text(strip=True) if nature_div else '校园招聘'
            industry_label = industry_div.get_text(strip=True) if industry_div else ''
            city = address_div.get_text(strip=True) if address_div else ''
            pub_date = time_div.get_text(strip=True) if time_div else ''

            a = item.find('a', href=True)
            link = base_url + a['href'] if a and not a['href'].startswith('http') else (a['href'] if a else '')

            if not company:
                continue
            industry = _classify_industry(company + ' ' + industry_label)
            if industries and industry not in industries:
                continue
            if _job_exists(db, company, position):
                continue
            _insert_job(db, {
                'company': company, 'position': position, 'city': city, 'salary': '',
                'deadline': pub_date, 'link': link,
                'notes': f'来源：{config["name"]} | 行业：{industry_label}',
                'source': 'scraper', 'industry': industry,
            })
            added += 1
        except:
            continue

    print(f'[YiJY] 爬取完成，新增 {added} 条')
    return added


def scrape_uibe(db, industries, config):
    """
    对外经济贸易大学自建JSP平台爬虫
    列表页URL: https://career.uibe.edu.cn/front/channel.jspa?channelId=764&parentId=625
    """
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    base_url = 'https://career.uibe.edu.cn'

    added = 0
    for page in range(1, 6):  # 爬前5页
        list_url = f'{base_url}/front/channel.jspa?channelId=764&parentId=625&page={page}'
        print(f'[UIBE] 爬取第{page}页: {list_url}')
        try:
            resp = requests.get(list_url, headers=HEADERS, timeout=30, verify=False)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'html.parser')
        except Exception as e:
            print(f'[UIBE] 请求失败: {e}')
            break

        # 找招聘信息链接
        items = soup.select('a[href*="zpxx.jspa"]')
        if not items:
            # 尝试找table中的链接
            items = soup.select('table a[href*="tid="]')

        for a in items[:20]:
            try:
                title = a.get_text(strip=True)
                href = a['href']
                if not title or len(title) < 5:
                    continue

                # 从标题提取公司名
                company = ''
                position = title
                match = re.match(r'^(.+?)(?:202\d届|招聘|岗位|校招)', title)
                if match:
                    company = match.group(1).strip()
                    company = re.sub(r'[|\s]+$', '', company)

                # 找同行中的日期
                parent = a.find_parent('tr') or a.find_parent('div')
                pub_date = ''
                if parent:
                    for text_node in parent.stripped_strings:
                        if re.match(r'20\d{2}-\d{2}-\d{2}', text_node):
                            pub_date = text_node
                            break

                link = base_url + href if not href.startswith('http') else href
                if not company:
                    company = title[:20]
                industry = _classify_industry(company + ' ' + title)
                if industries and industry not in industries:
                    continue
                if _job_exists(db, company, position):
                    position = title[:50]
                    if _job_exists(db, company, position):
                        continue
                _insert_job(db, {
                    'company': company, 'position': position, 'city': '', 'salary': '',
                    'deadline': pub_date, 'link': link,
                    'notes': f'来源：{config["name"]}',
                    'source': 'scraper', 'industry': industry,
                })
                added += 1
            except:
                continue

    print(f'[UIBE] 爬取完成，新增 {added} 条')
    return added


def scrape_sysu(db, industries, config):
    """
    中山大学（职派平台）爬虫
    列表页URL: https://career.sysu.edu.cn/job/search?page=0
    """
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    base_url = 'https://career.sysu.edu.cn'
    added = 0

    for page in range(0, 5):  # 爬前5页
        list_url = f'{base_url}/job/search?page={page}'
        print(f'[SYSU] 爬取第{page+1}页: {list_url}')
        try:
            resp = requests.get(list_url, headers=HEADERS, timeout=30, verify=False)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'html.parser')
        except Exception as e:
            print(f'[SYSU] 请求失败: {e}')
            break

        items = soup.select('li[data-id]')
        if not items:
            print(f'[SYSU] 第{page+1}页无数据')
            continue

        for item in items:
            try:
                company_a = item.select_one('div.company a')
                name_a = item.select_one('div.name a')
                salary_p = item.select_one('p.text-orange')
                date_span = item.select_one('div.name span')

                company = company_a.get_text(strip=True) if company_a else ''
                position = name_a.get_text(strip=True) if name_a else ''
                salary = salary_p.get_text(strip=True) if salary_p else ''
                pub_date = date_span.get_text(strip=True) if date_span else ''

                # 从span中提取日期
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', pub_date)
                pub_date = date_match.group(1) if date_match else ''

                a = name_a if name_a else company_a
                href = a['href'] if a and a.get('href') else ''
                link = base_url + href if href and not href.startswith('http') else href

                if not company or not position:
                    continue
                industry = _classify_industry(company + ' ' + position)
                if industries and industry not in industries:
                    continue
                if _job_exists(db, company, position):
                    continue

                # 提取城市
                city = ''
                for li in item.select('div.salary li'):
                    text = li.get_text(strip=True)
                    if re.match(r'.*[市省区县]', text) or len(text) <= 10:
                        city = text
                        break

                _insert_job(db, {
                    'company': company, 'position': position, 'city': city, 'salary': salary,
                    'deadline': pub_date, 'link': link,
                    'notes': f'来源：{config["name"]}',
                    'source': 'scraper', 'industry': industry,
                })
                added += 1
            except:
                continue

    print(f'[SYSU] 爬取完成，新增 {added} 条')
    return added
