// ── Vérification token ──
const token = localStorage.getItem('token');
const nom   = localStorage.getItem('nom');

if (!token) {
    window.location.href = 'login.html';
}

// ── Nom opérateur depuis login ──
if (nom) {
    document.getElementById('operateur').textContent = 'Opérateur : ' + nom;
}

// ── Déconnexion ──
function seDeconnecter() {
    localStorage.removeItem('token');
    localStorage.removeItem('nom');
    localStorage.removeItem('role');
    window.location.href = 'login.html';
}

// ── Horloge ──
function mettreAJourHeure() {
    const maintenant = new Date();
    document.getElementById('heure-actuelle').textContent =
        maintenant.toLocaleTimeString('fr-FR');
}
setInterval(mettreAJourHeure, 1000);
mettreAJourHeure();

// ── Compteur "mis à jour il y a Xs" ──
let secondes = 0;
setInterval(() => {
    secondes++;
    document.getElementById('derniere-maj').textContent = secondes;
}, 1000);

// ── WebSocket ──
const ws = new WebSocket('ws://127.0.0.1:8000/ws/etats');

ws.onopen = function() {
    console.log('✅ WebSocket connecté');
};

ws.onmessage = function(event) {
    const systemes = JSON.parse(event.data);
    mettreAJourInterface(systemes);
    secondes = 0;
};

ws.onerror = function() {
    console.log('❌ Erreur WebSocket');
};

ws.onclose = function() {
    console.log('🔌 WebSocket fermé');
};

// ── Mise à jour interface ──
function mettreAJourInterface(systemes) {
    let ok = 0, alarm = 0, fault = 0;

    systemes.forEach(sys => {
        const carte = document.getElementById('sys-' + sys.id);
        if (carte) {
            carte.className = 'carte-systeme ' + sys.etat.toLowerCase() + '-card';

            const badge = carte.querySelector('.badge');
            badge.className = 'badge badge-' + sys.etat.toLowerCase();

            const labels = { OK: 'OK', ALARM: 'ALARME', FAULT: 'DÉFAUT' };
            badge.textContent = labels[sys.etat] || sys.etat;

            carte.querySelector('.sys-heure').textContent = sys.timestamp;
        }

        if (sys.etat === 'OK')    ok++;
        if (sys.etat === 'ALARM') alarm++;
        if (sys.etat === 'FAULT') fault++;
    });

    // ── Compteurs ──
    document.getElementById('compteur-ok').textContent    = ok;
    document.getElementById('compteur-alarm').textContent = alarm;
    document.getElementById('compteur-fault').textContent = fault;
    document.getElementById('compteur-total').textContent = systemes.length;

    // ── Journal alarmes ──
    const tbody = document.getElementById('corps-alarmes');
    tbody.innerHTML = '';

    const alarmes = systemes.filter(
        sys => sys.etat === 'ALARM' || sys.etat === 'FAULT'
    );

    if (alarmes.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" style="text-align:center; color:#16a34a; padding:16px;">
                    ✓ Aucune alarme active
                </td>
            </tr>`;
    } else {
        alarmes.forEach(sys => {
            const labels    = { ALARM: 'ALARME', FAULT: 'DÉFAUT' };
            const badgeClass = sys.etat === 'ALARM' ? 'badge-alarm' : 'badge-fault';
            const typeTexte  = sys.etat === 'ALARM' ? 'Détection signal' : 'Relais ouvert';

            tbody.innerHTML += `
                <tr>
                    <td>${sys.timestamp}</td>
                    <td>${sys.nom}</td>
                    <td>${typeTexte}</td>
                    <td><span class="badge ${badgeClass}">${labels[sys.etat]}</span></td>
                    <td><button class="btn-acquitter" onclick="acquitter(this)">Acquitter</button></td>
                </tr>`;
        });
    }
}

// ── Acquitter ──
function acquitter(btn) {
    const ligne = btn.closest('tr');
    ligne.style.opacity = '0.4';
    btn.textContent = 'Acquitté ✓';
    btn.disabled = true;
}
function ouvrirPowerBI() {
    // ✅ Remplacez par le chemin exact de votre fichier .pbix
    const chemin = "C:\Users\hp\OneDrive\Bureau\\Tableau de Bord KPI  Supervision_CNS ESA.pbix";
    
    // Ouvre via un lien local
    window.open('powerbi:' + chemin);
}