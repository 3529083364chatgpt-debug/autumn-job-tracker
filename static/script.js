const API_BASE = '';
let jobs = [];
let syncInterval = null;

// ======== 初始化 ========
document.addEventListener('DOMContentLoaded', function() {
  loadJobs();
  loadStats();
  loadCities();
  bindEvents();
  startAutoSync();
});

// ======== 事件绑定 ========
function bindEvents() {
  document.getElementById('btn-toggle-form').addEventListener('click', toggleForm);
  document.getElementById('btn-cancel').addEventListener('click', toggleForm);
  document.getElementById('add-form').addEventListener('submit', handleAddJob);
  document.getElementById('edit-form').addEventListener('submit', handleEditJob);
  document.getElementById('btn-filter').addEventListener('click', handleFilter);
  document.getElementById('btn-reset').addEventListener('click', handleReset);
  document.getElementById('close-modal').addEventListener('click', closeModal);
  document.getElementById('btn-cancel-edit').addEventListener('click', closeModal);
  document.getElementById('edit-modal').addEventListener('click', function(e) {
    if (e.target === this) closeModal();
  });
  document.getElementById('filter-keyword').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') handleFilter();
  });
  document.getElementById('btn-export').addEventListener('click', handleExport);
  document.getElementById('btn-logout').addEventListener('click', handleLogout);
  document.getElementById('btn-scrape').addEventListener('click', handleScrape);
  if (document.getElementById('btn-scrape-all')) {
    document.getElementById('btn-scrape-all').addEventListener('click', handleScrapeAll);
  }
}

function toggleForm() {
  const panel = document.getElementById('form-panel');
  if (panel.style.display === 'none') {
    panel.style.display = 'block';
    panel.scrollIntoView({ behavior: 'smooth' });
  } else {
    panel.style.display = 'none';
    document.getElementById('add-form').reset();
  }
}

// ======== 加载数据 ========
async function loadJobs() {
  try {
    const status = document.getElementById('filter-status').value;
    const city = document.getElementById('filter-city').value;
    const industry = document.getElementById('filter-industry').value;
    const keyword = document.getElementById('filter-keyword').value;

    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (city) params.append('city', city);
    if (industry) params.append('industry', industry);
    if (keyword) params.append('keyword', keyword);

    const response = await fetch(API_BASE + '/api/jobs?' + params.toString());
    if (response.status === 401) {
      window.location.href = '/login';
      return;
    }
    if (response.ok) {
      jobs = await response.json();
      renderTable();
    }
  } catch (error) {
    console.error('加载数据失败:', error);
  }
}

async function loadStats() {
  try {
    const response = await fetch(API_BASE + '/api/stats');
    if (response.ok) {
      const stats = await response.json();
      updateStats(stats);
    }
  } catch (error) {
    console.error('加载统计失败:', error);
  }
}

async function loadCities() {
  try {
    const response = await fetch(API_BASE + '/api/cities');
    if (response.ok) {
      const cities = await response.json();
      const select = document.getElementById('filter-city');
      while (select.options.length > 1) select.remove(1);
      cities.forEach(city => {
        const option = document.createElement('option');
        option.value = city;
        option.textContent = city;
        select.appendChild(option);
      });
    }
  } catch (error) {
    console.error('加载城市列表失败:', error);
  }
}

// ======== 统计卡片 ========
function updateStats(stats) {
  document.getElementById('stat-total').textContent = stats.total;
  document.getElementById('stat-pending').textContent = stats.status_counts['未投'] || 0;
  document.getElementById('stat-interview').textContent =
    (stats.status_counts['笔试'] || 0) + (stats.status_counts['面试'] || 0);
  document.getElementById('stat-offer').textContent = stats.status_counts['OC'] || 0;
  document.getElementById('stat-urgent').textContent = stats.urgent;
}

// ======== 渲染表格 ========
function renderTable() {
  const tbody = document.getElementById('job-table-body');
  if (jobs.length === 0) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="10" class="empty-message">\u6682\u65E0\u6570\u636E\uFF0C\u70B9\u51FB\u4E0A\u65B9\u201C\u6DFB\u52A0\u62DB\u8058\u4FE1\u606F\u201D\u5F00\u59CB\u8BB0\u5F55</td></tr>';
    return;
  }

  tbody.innerHTML = jobs.map(job => {
    const industryClass = job.industry ? 'industry-' + job.industry : '';
    return `<tr>
      <td><span class="priority-badge priority-${job.priority}">${job.priority}</span></td>
      <td>
        ${job.link ? `<a href="${job.link}" target="_blank" class="company-link">${escapeHtml(job.company)}</a>` : escapeHtml(job.company)}
        ${job.notes ? `<div class="notes-preview" title="${escapeHtml(job.notes)}">${escapeHtml(job.notes)}</div>` : ''}
      </td>
      <td>${escapeHtml(job.position)}</td>
      <td>${escapeHtml(job.city || '-')}</td>
      <td>${job.industry ? `<span class="industry-badge ${industryClass}">${job.industry}</span>` : '-'}</td>
      <td>${escapeHtml(job.salary || '-')}</td>
      <td><span class="status-badge status-${job.status}">${job.status}</span></td>
      <td class="${getDeadlineClass(job.deadline)}">${job.deadline || '-'}</td>
      <td><span class="source-badge source-${job.source || 'manual'}">${job.source === 'scraper' ? '爬虫' : '手动'}</span></td>
      <td>
        <div class="actions">
          <button class="btn btn-secondary btn-sm" onclick="openEditModal(${job.id})">\u7F16\u8F91</button>
          <button class="btn btn-danger btn-sm" onclick="deleteJob(${job.id})">\u5220\u9664</button>
        </div>
      </td>
    </tr>`;
  }).join('');
}

// ======== 添加 ========
async function handleAddJob(e) {
  e.preventDefault();
  const form = e.target;
  const formData = new FormData(form);
  const data = Object.fromEntries(formData);
  data.priority = parseInt(data.priority);

  try {
    const response = await fetch(API_BASE + '/api/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (response.status === 401) { window.location.href = '/login'; return; }
    if (response.ok) {
      form.reset();
      toggleForm();
      loadJobs(); loadStats(); loadCities();
    } else {
      alert('\u6DFB\u52A0\u5931\u8D25\uFF0C\u8BF7\u91CD\u8BD5');
    }
  } catch (error) {
    alert('\u6DFB\u52A0\u5931\u8D25\uFF0C\u8BF7\u68C0\u67E5\u7F51\u7EDC');
  }
}

// ======== 编辑 ========
async function openEditModal(jobId) {
  try {
    const response = await fetch(API_BASE + '/api/jobs/' + jobId);
    if (response.status === 401) { window.location.href = '/login'; return; }
    if (response.ok) {
      const job = await response.json();
      const form = document.getElementById('edit-form');
      form.querySelector('[name="id"]').value = job.id;
      form.querySelector('[name="company"]').value = job.company;
      form.querySelector('[name="position"]').value = job.position;
      form.querySelector('[name="city"]').value = job.city || '';
      form.querySelector('[name="salary"]').value = job.salary || '';
      form.querySelector('[name="status"]').value = job.status;
      form.querySelector('[name="industry"]').value = job.industry || '';
      form.querySelector('[name="deadline"]').value = job.deadline || '';
      form.querySelector('[name="link"]').value = job.link || '';
      form.querySelector('[name="priority"]').value = job.priority;
      form.querySelector('[name="source"]').value = job.source || 'manual';
      form.querySelector('[name="notes"]').value = job.notes || '';
      document.getElementById('edit-modal').style.display = 'flex';
    }
  } catch (error) {
    console.error('\u52A0\u8F7D\u7F16\u8F91\u6570\u636E\u5931\u8D25:', error);
  }
}

async function handleEditJob(e) {
  e.preventDefault();
  const form = e.target;
  const formData = new FormData(form);
  const data = Object.fromEntries(formData);
  const jobId = data.id;
  delete data.id;
  data.priority = parseInt(data.priority);

  try {
    const response = await fetch(API_BASE + '/api/jobs/' + jobId, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (response.status === 401) { window.location.href = '/login'; return; }
    if (response.ok) {
      closeModal();
      loadJobs(); loadStats();
    } else {
      alert('\u66F4\u65B0\u5931\u8D25\uFF0C\u8BF7\u91CD\u8BD5');
    }
  } catch (error) {
    alert('\u66F4\u65B0\u5931\u8D25\uFF0C\u8BF7\u68C0\u67E5\u7F51\u7EDC');
  }
}

function closeModal() {
  document.getElementById('edit-modal').style.display = 'none';
}

// ======== 删除 ========
async function deleteJob(jobId) {
  if (!confirm('\u786E\u5B9A\u8981\u5220\u9664\u8FD9\u6761\u8BB0\u5F55\u5417\uFF1F')) return;
  try {
    const response = await fetch(API_BASE + '/api/jobs/' + jobId, { method: 'DELETE' });
    if (response.status === 401) { window.location.href = '/login'; return; }
    if (response.ok) {
      loadJobs(); loadStats();
    } else {
      alert('\u5220\u9664\u5931\u8D25');
    }
  } catch (error) {
    alert('\u5220\u9664\u5931\u8D25\uFF0C\u8BF7\u68C0\u67E5\u7F51\u7EDC');
  }
}

// ======== 筛选 ========
function handleFilter() { loadJobs(); }

function handleReset() {
  document.getElementById('filter-status').value = '';
  document.getElementById('filter-industry').value = '';
  document.getElementById('filter-city').value = '';
  document.getElementById('filter-keyword').value = '';
  loadJobs();
}

// ======== 导出 CSV ========
function handleExport() {
  const status = document.getElementById('filter-status').value;
  const city = document.getElementById('filter-city').value;
  const industry = document.getElementById('filter-industry').value;
  const keyword = document.getElementById('filter-keyword').value;

  const params = new URLSearchParams();
  if (status) params.append('status', status);
  if (city) params.append('city', city);
  if (industry) params.append('industry', industry);
  if (keyword) params.append('keyword', keyword);

  window.location.href = API_BASE + '/api/export?' + params.toString();
}

// ======== 登出 ========
async function handleLogout() {
  try {
    await fetch(API_BASE + '/api/logout', { method: 'POST' });
    window.location.href = '/login';
  } catch (error) {
    console.error('\u767B\u51FA\u5931\u8D25:', error);
  }
}

// ======== 数据抓取 ========
async function handleScrape() {
  const source = document.getElementById('scraper-source').value;
  await startScrape([source]);
}

async function handleScrapeAll() {
  await startScrape(['all']);
}

async function startScrape(sources) {
  const btn = document.getElementById('btn-scrape');
  const btnAll = document.getElementById('btn-scrape-all');
  const originalText = btn ? btn.innerHTML : '';
  const originalAllText = btnAll ? btnAll.innerHTML : '';
  if (btn) { btn.innerHTML = '抓取中...'; btn.disabled = true; }
  if (btnAll) { btnAll.innerHTML = '抓取中...'; btnAll.disabled = true; }

  try {
    // Start background scraping
    const response = await fetch(API_BASE + '/api/scraper/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sources: sources, industries: ['金融', '互联网', '国央企'] })
    });
    if (response.status === 401) { window.location.href = '/login'; return; }
    const data = await response.json();

    if (data.status === 'running') {
      alert('爬虫正在运行中，请稍候');
      return;
    }

    if (data.status === 'started') {
      // Poll for status
      pollScrapeStatus(btn, originalText, btnAll, originalAllText);
    }
  } catch (error) {
    alert('请求失败，请检查网络');
    if (btn) { btn.innerHTML = originalText; btn.disabled = false; }
    if (btnAll) { btnAll.innerHTML = originalAllText; btnAll.disabled = false; }
  }
}

async function pollScrapeStatus(btn, originalText, btnAll, originalAllText) {
  const pollInterval = setInterval(async function() {
    try {
      const response = await fetch(API_BASE + '/api/scraper/status');
      if (!response.ok) return;
      const status = await response.json();

      if (!status.running) {
        clearInterval(pollInterval);
        if (btn) { btn.innerHTML = originalText; btn.disabled = false; }
        if (btnAll) { btnAll.innerHTML = originalAllText; btnAll.disabled = false; }

        let msg = '';
        let totalAdded = 0;
        let errors = [];
        status.results.forEach(function(r) {
          if (r.status === 'success') {
            totalAdded += r.added;
          } else {
            errors.push(r.source + ': ' + (r.message || '失败'));
          }
        });

        if (totalAdded > 0) {
          msg = '抓取完成！共新增 ' + totalAdded + ' 条职位';
          status.results.forEach(function(r) {
            if (r.status === 'success') {
              msg += '\n' + r.source + ': +' + r.added + '条';
            }
          });
        } else {
          msg = '没有抓取到新数据';
        }
        if (errors.length > 0) {
          msg += '\n\n以下渠道失败:\n' + errors.join('\n');
        }
        alert(msg);
        loadJobs(); loadStats(); loadCities();
      }
    } catch (e) {
      // ignore poll errors, keep trying
    }
  }, 3000); // poll every 3 seconds
}

// ======== 自动同步 ========
function startAutoSync() {
  syncInterval = setInterval(function() {
    loadJobs(); loadStats();
    document.getElementById('last-sync').textContent = '\u521A\u521A\u66F4\u65B0';
  }, 30000);
}

// ======== 工具函数 ========
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text || '';
  return div.innerHTML;
}

function getDeadlineClass(deadline) {
  if (!deadline) return '';
  const now = new Date();
  const dl = new Date(deadline);
  const diff = (dl - now) / (1000 * 60 * 60 * 24);
  if (diff < 3) return 'deadline-urgent';
  if (diff < 7) return 'deadline-soon';
  return '';
}
