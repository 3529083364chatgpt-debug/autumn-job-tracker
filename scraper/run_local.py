"""
本地爬虫脚本 - 在本地运行所有爬虫，导出为JSON文件
用法: python -m scraper.run_local
导出文件: scraped_data.json (可导入到平台)
"""
import sys
import os
import json
import sqlite3
from datetime import datetime

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.platform_spiders import scrape_ncss, scrape_niuke, scrape_yjszp
from scraper.university_spiders import scrape_university
from scraper.config import UNIVERSITY_SOURCES

def main():
    industries = ['金融', '互联网', '国央企']

    # Use in-memory DB
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

    # NCSS
    print('='*50)
    print('正在爬取: NCSS（国家大学生就业服务平台）')
    print('='*50)
    try:
        count = scrape_ncss(db, industries, max_pages=5)
        results.append({'source': 'NCSS', 'added': count, 'status': 'success'})
    except Exception as e:
        results.append({'source': 'NCSS', 'added': 0, 'status': 'error', 'message': str(e)})
        print(f'NCSS 失败: {e}')

    # Niuke
    print()
    print('='*50)
    print('正在爬取: 牛客网校招日历')
    print('='*50)
    try:
        count = scrape_niuke(db, industries)
        results.append({'source': '牛客网', 'added': count, 'status': 'success'})
    except Exception as e:
        results.append({'source': '牛客网', 'added': 0, 'status': 'error', 'message': str(e)})
        print(f'牛客网 失败: {e}')

    # YJSZP
    print()
    print('='*50)
    print('正在爬取: 应届生求职网')
    print('='*50)
    try:
        count = scrape_yjszp(db, industries)
        results.append({'source': '应届生求职网', 'added': count, 'status': 'success'})
    except Exception as e:
        results.append({'source': '应届生求职网', 'added': 0, 'status': 'error', 'message': str(e)})
        print(f'应届生求职网 失败: {e}')

    # University sources
    for key, config in UNIVERSITY_SOURCES.items():
        if not config.get('enabled'):
            continue
        name = config.get('name', key)
        print()
        print('='*50)
        print(f'正在爬取: {name}')
        print('='*50)
        try:
            count = scrape_university(key, industries, db)
            results.append({'source': name, 'added': count, 'status': 'success'})
        except Exception as e:
            results.append({'source': name, 'added': 0, 'status': 'error', 'message': str(e)})
            print(f'{name} 失败: {e}')

    # Export
    rows = db.execute('SELECT company, position, city, salary, status, deadline, link, notes, priority, source, industry FROM jobs').fetchall()
    jobs = []
    for row in rows:
        jobs.append({
            'company': row[0],
            'position': row[1],
            'city': row[2],
            'salary': row[3],
            'status': row[4],
            'deadline': row[5],
            'link': row[6],
            'notes': row[7],
            'priority': row[8],
            'source': row[9],
            'industry': row[10],
        })

    output = {
        'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total': len(jobs),
        'scrape_results': results,
        'jobs': jobs
    }

    output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scraped_data.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    db.close()

    print()
    print('='*50)
    print('抓取完成！')
    print('='*50)
    for r in results:
        status = 'OK' if r['status'] == 'success' else 'FAIL'
        print(f'  {r["source"]}: {r["added"]} 条 [{status}]')
        if r.get('message'):
            print(f'    错误: {r["message"]}')
    print(f'\n共 {len(jobs)} 条数据已导出到: {output_path}')
    print(f'\n下一步: 打开平台 → 点击“导入数据” → 选择 scraped_data.json')

if __name__ == '__main__':
    main()
