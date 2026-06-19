// dashboard.js — Version 2 : acquittement réel + prédictions enrichies

// ── Vérification token ──
const token = localStorage.getItem('token');
const nom   = localStorage.getItem('nom');
if (!token) window.location.href = 'login.html';
if (nom) document.getElementById('operateur').textContent = 'Opérateur : ' + nom;

function seDeconnecter() {
    localStorage.removeItem('token');
    localStorage.removeItem('nom');
    localStorage.removeItem('role');
    window.location.href = 'login.html';
}

// ── Horloge ──
function mettreAJourHeure() {
    document.getElementById('heure-actuelle').textContent =
        new Date().toLocaleTimeString('fr-FR');
}
setInterval(mettreAJourHeure, 1000);
mettreAJourHeure();

// ── Compteur mis à jour ──
let secondes = 0;
setInterval(() => {
    secondes++;
    document.getElementById('derniere-maj').textContent = secondes;
}, 1000);

// ════════════════════════════════
// SON D'ALARME
// ════════════════════════════════
let audioContext = null;
let alarmeActive = false;

function initialiserAudio() {
    if (!audioContext)
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
}

function jouerSonAlarme() {
    if (!audioContext || alarmeActive) return;
    alarmeActive = true;
    function bip() {
        if (!alarmeActive) return;
        const osc  = audioContext.createOscillator();
        const gain = audioContext.createGain();
        osc.connect(gain);
        gain.connect(audioContext.destination);
        osc.type = 'square';
        osc.frequency.value = 880;
        gain.gain.setValueAtTime(0.3, audioContext.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.4);
        osc.start(audioContext.currentTime);
        osc.stop(audioContext.currentTime + 0.4);
        if (alarmeActive) setTimeout(bip, 1000);
    }
    bip();
}

function arreterSonAlarme() { alarmeActive = false; }

document.addEventListener('click', initialiserAudio, { once: true });

// ════════════════════════════════
// WEBSOCKET
// ════════════════════════════════
const ws = new WebSocket('ws://127.0.0.1:8000/ws/etats');

ws.onopen    = () => console.log('✅ WebSocket connecté');
ws.onerror   = () => console.log('❌ Erreur WebSocket');
ws.onmessage = function(event) {
    const systemes = JSON.parse(event.data);
    mettreAJourInterface(systemes);
    secondes = 0;
};

// ════════════════════════════════
// MISE À JOUR INTERFACE
// ════════════════════════════════
function mettreAJourInterface(systemes) {
    let ok = 0, alarm = 0, fault = 0;
    let yaAlarme = false;

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
        if (sys.etat === 'ALARM') { alarm++; yaAlarme = true; }
        if (sys.etat === 'FAULT') { fault++; yaAlarme = true; }
    });

    document.getElementById('compteur-ok').textContent    = ok;
    document.getElementById('compteur-alarm').textContent = alarm;
    document.getElementById('compteur-fault').textContent = fault;
    document.getElementById('compteur-total').textContent = systemes.length;

    if (yaAlarme) jouerSonAlarme();
    else arreterSonAlarme();

    // ── Journal alarmes avec bouton Acquitter ──
    const tbody   = document.getElementById('corps-alarmes');
    tbody.innerHTML = '';

    const alarmes = systemes.filter(s => s.etat === 'ALARM' || s.etat === 'FAULT');

    if (alarmes.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" style="text-align:center;color:#16a34a;padding:16px;">
                    ✓ Aucune alarme active
                </td>
            </tr>`;
        return;
    }

    alarmes.forEach(sys => {
        const heureReelle = new Date().toLocaleString('fr-FR', {
            day: '2-digit', month: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        });
        const badgeClass = sys.etat === 'ALARM' ? 'badge-alarm' : 'badge-fault';
        const labels     = { ALARM: 'ALARME', FAULT: 'DÉFAUT' };
        const typeTexte  = sys.etat === 'ALARM' ? 'Détection signal' : 'Relais ouvert';

        tbody.innerHTML += `
            <tr id="ligne-${sys.id}">
                <td>${heureReelle}</td>
                <td>${sys.nom}</td>
                <td>${typeTexte}</td>
                <td><span class="badge ${badgeClass}">${labels[sys.etat]}</span></td>
                <td>
                    <button class="btn-acquitter"
                            onclick="acquitterDepuisWS(${sys.id}, '${sys.nom}', this)">
                        Acquitter
                    </button>
                </td>
            </tr>`;
    });
}

// ════════════════════════════════
// ✅ JOURNAL ALARMES DEPUIS LA BDD
// Chargé séparément — avec vrai bouton acquitter
// ════════════════════════════════
async function chargerAlarmesBDD() {
    try {
        const response = await fetch('http://127.0.0.1:8000/api/alarmes', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (!response.ok) return;
        const alarmes = await response.json();
        afficherAlarmesBDD(alarmes);
    } catch(e) {
        console.error('Erreur chargement alarmes:', e);
    }
}

function afficherAlarmesBDD(alarmes) {
    const tbody = document.getElementById('corps-alarmes-bdd');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (alarmes.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" style="text-align:center;color:#16a34a;padding:16px;">
                    ✓ Aucune alarme non acquittée
                </td>
            </tr>`;
        return;
    }

    alarmes.forEach(sys => {
    const badgeClass = sys.etat === 'ALARM' ? 'badge-alarm' : 'badge-fault';
    const labels     = { ALARM: 'ALARME', FAULT: 'DÉFAUT' };
    const typeTexte  = sys.etat === 'ALARM' ? 'Détection signal' : 'Relais ouvert';
    
    // ✅ Heure réelle au moment de l'affichage
    const heureReelle = new Date().toLocaleString('fr-FR', {
        day:    '2-digit',
        month:  '2-digit',
        hour:   '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });

    tbody.innerHTML += `
        <tr id="ligne-${sys.id}">
            <td>${heureReelle}</td>
            <td>${sys.nom}</td>
            <td>${typeTexte}</td>
            <td><span class="badge ${badgeClass}">${labels[sys.etat]}</span></td>
            <td>
                <button class="btn-acquitter" 
                        onclick="acquitterDepuisWS('${sys.id}', '${sys.nom}', this)">
                    Acquitter
                </button>
            </td>
        </tr>`;
});
}

// ════════════════════════════════
// ✅ ACQUITTEMENT RÉEL — appel API
// Avant : btn.disabled = true  (rien en BDD)
// Après : PUT /api/alarmes/{id}/acquitter avec token JWT
// ════════════════════════════════
async function acquitterDepuisWS(systemeId, systemeNom, btn) {
    btn.textContent = 'En cours...';
    btn.disabled    = true;

    try {
        // 1. Chercher l'alarme active de ce système en BDD
        const response = await fetch('http://127.0.0.1:8000/api/alarmes', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        const alarmes = await response.json();
        
        // 2. Trouver l'alarme correspondant au système
        const alarme = alarmes.find(a => a.systeme_nom === systemeNom);
        
        if (!alarme) {
            btn.textContent = 'Acquitter';
            btn.disabled    = false;
            return;
        }

        // 3. Acquitter via l'API
        const r2 = await fetch(
            `http://127.0.0.1:8000/api/alarmes/${alarme.id}/acquitter`,
            {
                method:  'PUT',
                headers: { 'Authorization': 'Bearer ' + token }
            }
        );

        if (r2.ok) {
            const ligne = btn.closest('tr');
            ligne.style.transition = 'opacity 0.5s';
            ligne.style.opacity    = '0';
            setTimeout(() => ligne.remove(), 500);
            const restants = document.querySelectorAll('.btn-acquitter:not(:disabled)');
            if (restants.length === 0) arreterSonAlarme();
        } else {
            btn.textContent = 'Acquitter';
            btn.disabled    = false;
        }
    } catch(e) {
        btn.textContent = 'Acquitter';
        btn.disabled    = false;
        console.error('Erreur acquittement:', e);
    }
}

// Rafraîchir le journal toutes les 15s
chargerAlarmesBDD();
setInterval(chargerAlarmesBDD, 15000);

// ════════════════════════════════
// ✅ PRÉDICTIONS IA ENRICHIES
// Nouveaux champs : tendance, consecutif, duree_moy, heure_creuse
// ════════════════════════════════
async function chargerPredictions() {
    try {
        const response = await fetch('http://127.0.0.1:8000/api/predictions', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        const predictions = await response.json();
        afficherPredictions(predictions);
        verifierAlertesSonores(predictions);
    } catch(e) {
        console.error('Erreur prédictions:', e);
    }
}

function verifierAlertesSonores(predictions) {
    if (predictions.some(p => p.niveau === 'CRITIQUE')) jouerSonAlarme();
}

function afficherPredictions(predictions) {
    const grille = document.getElementById('grille-predictions');
    if (!grille) return;
    grille.innerHTML = '';

    const couleurs = {
        'CRITIQUE': { bg: '#fee2e2', border: '#dc2626', text: '#991b1b' },
        'ÉLEVÉ':    { bg: '#fef3c7', border: '#d97706', text: '#92400e' },
        'MOYEN':    { bg: '#dbeafe', border: '#2563eb', text: '#1e40af' },
        'FAIBLE':   { bg: '#dcfce7', border: '#16a34a', text: '#166534' },
    };

    predictions.forEach(pred => {
        const c = couleurs[pred.niveau] || couleurs['FAIBLE'];

        // ✅ Badge tendance
        const tendanceTxt = pred.tendance === 1
            ? `<span style="background:#fee2e2;color:#991b1b;padding:2px 8px;border-radius:99px;font-size:10px;font-weight:600;">📈 Dégradation</span>`
            : `<span style="background:#dcfce7;color:#166534;padding:2px 8px;border-radius:99px;font-size:10px;font-weight:600;">📉 Stable</span>`;

        // ✅ Durée moyenne panne
        const dureeMin = Math.floor(pred.duree_moy / 60);
        const dureeSec = Math.round(pred.duree_moy % 60);
        const dureeTxt = pred.duree_moy > 0
            ? `Moy. panne : ${dureeMin > 0 ? dureeMin + 'min ' : ''}${dureeSec}s`
            : 'Aucune panne historique';

        // ✅ Heure creuse
        const heureTxt = pred.heure_creuse
            ? `<span style="color:#6b7280;font-size:10px;">🌙 Heure creuse</span>`
            : '';

        // ✅ Pannes consécutives
        const consecTxt = pred.consecutif > 0
            ? `<span style="color:${c.text};font-size:10px;font-weight:600;">${pred.consecutif} panne(s) consécutive(s)</span>`
            : '';

        grille.innerHTML += `
            <div style="
                background:${c.bg};
                border:1px solid ${c.border};
                border-left:4px solid ${c.border};
                border-radius:10px;
                padding:14px 16px;
            ">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">
                    <p style="font-size:14px;font-weight:600;color:#1a1a1a;">${pred.systeme_nom}</p>
                    ${heureTxt}
                </div>
                <p style="font-size:11px;color:#6b7280;margin:0 0 4px;">Risque de panne</p>
                <p style="font-size:24px;font-weight:700;color:${c.border};margin:0 0 6px;">
                    ${Math.round(pred.probabilite * 100)}%
                </p>
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                    <span style="font-size:11px;font-weight:600;padding:3px 10px;border-radius:99px;background:${c.border};color:white;">
                        ${pred.niveau}
                    </span>
                    ${tendanceTxt}
                </div>
                ${consecTxt ? `<p style="margin:4px 0;">${consecTxt}</p>` : ''}
                <p style="font-size:11px;color:${c.text};margin:6px 0 2px;">${pred.message}</p>
                <p style="font-size:10px;color:#9ca3af;margin:0;">${dureeTxt}</p>
            </div>`;
    });
}


chargerPredictions();
setInterval(chargerPredictions, 30000);