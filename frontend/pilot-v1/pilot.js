const views = [...document.querySelectorAll('.view')];
const navItems = [...document.querySelectorAll('.nav-item')];
const title = document.getElementById('pageTitle');
const modal = document.getElementById('missionModal');
const labels = {
  command: 'Command',
  mission: 'Missão ativa',
  memory: 'Memória organizacional',
  learning: 'Aprendizagem',
  evidence: 'Evidência',
  pilot: 'Pilot Mode'
};

function showView(name) {
  views.forEach(v => v.classList.toggle('active', v.id === `view-${name}`));
  navItems.forEach(n => n.classList.toggle('active', n.dataset.view === name));
  if (labels[name]) title.textContent = labels[name];
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

navItems.forEach(item => item.addEventListener('click', () => showView(item.dataset.view)));
document.querySelectorAll('[data-goto]').forEach(el => el.addEventListener('click', () => showView(el.dataset.goto)));

document.getElementById('newMissionBtn').addEventListener('click', () => modal.classList.remove('hidden'));
document.getElementById('closeModal').addEventListener('click', () => modal.classList.add('hidden'));
modal.addEventListener('click', event => { if (event.target === modal) modal.classList.add('hidden'); });

document.getElementById('refreshBtn').addEventListener('click', () => window.location.reload());

async function checkHealth() {
  const dot = document.getElementById('healthDot');
  const label = document.getElementById('healthLabel');
  try {
    const response = await fetch('/health', { cache: 'no-store' });
    if (!response.ok) throw new Error('healthcheck failed');
    dot.classList.add('ok');
    label.textContent = 'operacional';
  } catch (error) {
    dot.classList.add('bad');
    label.textContent = 'indisponível';
  }
}

checkHealth();
