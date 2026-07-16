const API_BASE = '';
let jobs = [];
let currentPage = 1;
let totalPages = 1;
let totalJobs = 0;
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
  if (document.getElementById('btn-import')) {
    document.getElementById('btn-import').addEventListener('click', handleImport);
  }
  if (document.getElementById('btn-export-json')) {
    document.getElementById('btn-export-json').addEventListener('click', handleExport);
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
    params.append('page', currentPage);
    params.append('per_page', 50);

    const response = await fetch(API_BASE + '/api/jobs?' + params.toString());
    if (response.status === 401) {
      window.location.href = '/login';
      return;
    }
    if (response.ok) {
      const data = await response.json();
      jobs = data.jobs || [];
      totalJobs = data.total || 0;
      totalPages = data.total_pages || 1;
      renderTable();
      renderPagination();
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
    tbody.innerHTML = '<tr class="empty-row"><td colspan="10" class="empty-message">暂无数据，点击上方"添加招聘信息"开始记录</td></tr>';
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
          <button class="btn btn-secondary btn-sm" onclick="openEditModal(${job.id})">编辑</button>
          <button class="btn btn-secondary btn-sm" onclick="window.open('/job/${job.id}/interviews', '_self')">面经</button>
          <button class="btn btn-danger btn-sm" onclick="deleteJob(${job.id})">删除</button>
        </div>
      </td>
    </tr>`;
  }).join('');
}

// ======== 分页 ========
function renderPagination() {
  const paginationDiv = document.getElementById('pagination');
  if (!paginationDiv) return;

  if (totalPages <= 1) {
    paginationDiv.innerHTML = '<span class="pagination-info">共 ' + totalJobs + ' 条记录</span>';
    return;
  }

  let html = '';

  // 上一页按钮
  html += `<button ${currentPage === 1 ? 'disabled' : ''} onclick="goToPage(${currentPage - 1})">上一页</button>`;

  // 页码按钮
  let startPage = Math.max(1, currentPage - 2);
  let endPage = Math.min(totalPages, currentPage + 2);

  if (startPage > 1) {
    html += `<button onclick="goToPage(1)">1</button>`;
    if (startPage > 2) {
      html += '<span class="pagination-info">...</span>';
    }
  }

  for (let i = startPage; i <= endPage; i++) {
    html += `<button class="${i === currentPage ? 'active' : ''}" onclick="goToPage(${i})">${i}</button>`;
  }

  if (endPage < totalPages) {
    if (endPage < totalPages - 1) {
      html += '<span class="pagination-info">...</span>';
    }
    html += `<button onclick="goToPage(${totalPages})">${totalPages}</button>`;
  }

  // 下一页按钮
  html += `<button ${currentPage === totalPages ? 'disabled' : ''} onclick="goToPage(${currentPage + 1})">下一页</button>`;

  // 信息
  let startNum = (currentPage - 1) * 50 + 1;
  let endNum = Math.min(currentPage * 50, totalJobs);
  html += `<span class="pagination-info">${startNum}-${endNum} / 共 ${totalJobs} 条</span>`;

  paginationDiv.innerHTML = html;
}

function goToPage(page) {
  if (page < 1 || page > totalPages || page === currentPage) return;
  currentPage = page;
  loadJobs();
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
      currentPage = 1;
      loadJobs(); loadStats(); loadCities();
    } else {
      alert('添加失败，请重试');
    }
  } catch (error) {
    alert('添加失败，请检查网络');
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
    console.error('加载编辑数据失败:', error);
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
      alert('更新失败，请重试');
    }
  } catch (error) {
    alert('更新失败，请检查网络');
  }
}

function closeModal() {
  document.getElementById('edit-modal').style.display = 'none';
}

// ======== 删除 ========
async function deleteJob(jobId) {
  if (!confirm('确定要删除这条记录吗？')) return;
  try {
    const response = await fetch(API_BASE + '/api/jobs/' + jobId, { method: 'DELETE' });
    if (response.status === 401) { window.location.href = '/login'; return; }
    if (response.ok) {
      loadJobs(); loadStats();
    } else {
      alert('删除失败');
    }
  } catch (error) {
    alert('删除失败，请检查网络');
  }
}

// ======== 筛选 ========
function handleFilter() { currentPage = 1; loadJobs(); }

function handleReset() {
  document.getElementById('filter-status').value = '';
  document.getElementById('filter-industry').value = '';
  document.getElementById('filter-city').value = '';
  document.getElementById('filter-keyword').value = '';
  currentPage = 1;
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
    console.error('登出失败:', error);
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


// ======== 导入/导出 ========
function handleImport() {
  var input = document.createElement('input');
  input.type = 'file';
  input.accept = '.json';
  input.onchange = function(e) {
    var file = e.target.files[0];
    if (!file) return;
    var formData = new FormData();
    formData.append('file', file);
    fetch(API_BASE + '/api/jobs/import', { method: 'POST', body: formData })
      .then(function(r) {
        if (r.status === 401) { window.location.href = '/login'; return; }
        return r.json();
      })
      .then(function(data) {
        if (data.error) { alert('导入失败: ' + data.error); return; }
        alert('导入成功！新增 ' + data.added + ' 条，跳过重复 ' + data.skipped + ' 条');
        currentPage = 1;
        loadJobs(); loadStats(); loadCities();
      })
      .catch(function() { alert('导入请求失败'); });
  };
  input.click();
}

function handleExport() {
  window.location.href = API_BASE + '/api/jobs/export';
}

// ======== 自动同步 ========
function startAutoSync() {
  syncInterval = setInterval(function() {
    loadJobs(); loadStats();
    document.getElementById('last-sync').textContent = '刚刚更新';
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
