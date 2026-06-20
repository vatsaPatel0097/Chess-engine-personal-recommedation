function showTab(tabName, btn) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));

    document.getElementById('tab-' + tabName).classList.add('active');
    btn.classList.add('active');
}

function submitAnalysis(e) {
    var pgn = document.getElementById('pgn').value.trim();
    if (!pgn) {
        alert('Please paste a PGN first');
        e.preventDefault();
        return;
    }
    document.getElementById('loading-overlay').classList.remove('hidden');
    document.getElementById('analyzeBtn').disabled = true;
}
