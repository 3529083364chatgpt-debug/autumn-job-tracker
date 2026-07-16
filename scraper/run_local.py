"""
一键爬取并上传到平台
用法: python -m scraper.run_local
或者双击: 一键抓取.bat
"""
import sys
import os
import json
import sqlite3
import requests
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.platform_spiders import scrape_ncss, scrape_niuke, scrape_yjszp
from scraper.university_spiders import scrape_university
from scraper.config import UNIVERSITY_SOURCES

# ===== 配置 =====
PLATFORM_URL = 'https://autumn-job-tracker.onrender.com'
PLATFORM_PASSWORD = 'qiuzhao2026'


def scrape_all():
    """运行所有爬虫，返回职位列表"""
    industries = ['金融', '互联网', '国央企']

    db = sqlite3.connect(':memory:')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL, position TEXT NOT NULL, city TEXT, salary TEXT,
            status TEXT DEFAULT '未投', deadline TEXT, link TEXT, notes TEXT,
            priority INTEGER DEFAULT 3, source TEXT DEFAULT 'manual',
            industry TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    db.commit()

    results = []
    sources = [
        ('NCSS（国聘）', lambda: scrape_ncss(db, industries, max_pages=5)),
        ('牛客网', lambda: scrape_niuke(db, industries)),
        ('应届生求职网', lambda: scrape_yjszp(db, industries)),
    ]
    for key, config in UNIVERSITY_SOURCES.items():
        if config.get('enabled'):
            name = config.get('name', key)
            sources.append((name, lambda k=key: scrape_university(k, industries, db)))

    for name, func in sources:
        print(f'\n>>> 正在爬取: {name}')
        try:
            count = func()
            results.append({'source': name, 'added': count, 'status': 'success'})
            print(f'    完成: {count} 条')
        except Exception as e:
            results.append({'source': name, 'added': 0, 'status': 'error', 'message': str(e)})
            print(f'    失败: {e}')

    rows = db.execute('SELECT company, position, city, salary, deadline, link, notes, industry FROM jobs').fetchall()
    jobs = []
    for row in rows:
        jobs.append({
            'company': row[0], 'position': row[1], 'city': row[2],
            'salary': row[3], 'deadline': row[4], 'link': row[5],
            'notes': row[6], 'industry': row[7],
        })
    db.close()

    # Save locally too
    output = {
        'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total': len(jobs),
        'scrape_results': results,
        'jobs': jobs
    }
    output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scraped_data.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'\n本地备份已保存: {output_path}')

    return jobs, results


def upload_to_platform(jobs):
    """上传到线上平台"""
    print(f'\n>>> 正在上传到平台: {PLATFORM_URL}')
    try:
        s = requests.Session()

        # Wake up the server (Render free tier sleeps)
        print('    唤醒服务器...')
        try:
            s.get(PLATFORM_URL, timeout=15)
        except:
            pass

        # Login
        r = s.post(PLATFORM_URL + '/api/login', json={'password': PLATFORM_PASSWORD}, timeout=15)
        if r.status_code != 200 or not r.json().get('success'):
            print('    登录失败!')
            return False
        print('    登录成功')

        # Upload
        upload_data = json.dumps({'jobs': jobs}, ensure_ascii=False)
        r = s.post(PLATFORM_URL + '/api/jobs/import',
                    files={'file': ('scraped_data.json', upload_data, 'application/json')},
                    timeout=30)
        if r.status_code == 401:
            print('    认证失败')
            return False

        result = r.json()
        if result.get('success'):
            print(f'    上传成功! 新增 {result["added"]} 条, 跳过重复 {result["skipped"]} 条')
            return True
        else:
            print(f'    上传失败: {result.get("error", "未知错误")}')
            return False
    except requests.exceptions.Timeout:
        print('    上传超时，服务器可能还在启动中，请稍后重试')
        return False
    except Exception as e:
        print(f'    上传失败: {e}')
        return False


def main():
    print('=' * 55)
    print('  秋招信息追踪 - 一键抓取工具')
    print(f'  时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 55)

    # Step 1: Scrape
    jobs, results = scrape_all()

    if not jobs:
        print('\n没有抓取到任何数据')
        return

    # Summary
    print('\n' + '=' * 55)
    print('  爬取汇总')
    print('=' * 55)
    for r in results:
        tag = 'OK' if r['status'] == 'success' else 'FAIL'
        print(f'  {r["source"]}: {r["added"]} 条 [{tag}]')
    print(f'  总计: {len(jobs)} 条')

    # Step 2: Upload
    print('\n' + '=' * 55)
    success = upload_to_platform(jobs)

    # Final
    print('\n' + '=' * 55)
    if success:
        print('  全部完成! 请打开平台查看数据:')
        print(f'  {PLATFORM_URL}')
    else:
        print('  爬取完成但上传失败')
        print('  你可以手动导入 scraped_data.json 到平台')
    print('=' * 55)

    input('\n按回车键退出...')


if __name__ == '__main__':
    main()