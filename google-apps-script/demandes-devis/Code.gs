/** Alexis Événementiel — réception des demandes de devis du site alexisevenementiel.fr
 *
 * Le formulaire « Ma demande de devis » (catalogue.html) envoie chaque demande ici (doPost).
 * Pour chaque demande :
 *   1. une ligne dans le tableau Google Sheets « Demandes de devis » (historique + suivi) ;
 *   2. un événement dans l'agenda dédié « Demandes de devis » (si une date est indiquée) ;
 *   3. un e-mail de notification à NOTIF_EMAIL (« Répondre » écrit directement au client).
 * La demande est toujours enregistrée en premier : si l'agenda ou l'e-mail échouent,
 * la ligne reste dans le tableau avec l'erreur dans la colonne « Suivi ».
 *
 * Installation : voir LISEZ-MOI.md (même dossier). Exécuter installer() une fois, puis testerDemande().
 * Aucun identifiant secret dans ce fichier : les ID du tableau et de l'agenda sont dans les propriétés du script.
 */
const CONFIG = {
  NOM: 'Alexis Événementiel',
  NOTIF_EMAIL: 'contact@alexisevenementiel.fr',   // reçoit une notification par demande
  AGENDA_NOM: 'Demandes de devis',
  TABLEAU_NOM: 'Demandes de devis — Alexis Événementiel',
  ONGLET: 'Demandes',
  FUSEAU: 'Europe/Paris',
  RECAP_CLIENT: false,      // true = envoie aussi un accusé de réception au client
  MAX_PAR_HEURE: 30,        // garde-fou anti-spam (toutes demandes confondues)
  DELAI_MIN_MS: 3000        // formulaire rempli en moins de 3 s = robot
};

const ENTETES = ['Reçu le', 'Référence', 'Statut', 'Prénom', 'Nom', 'E-mail', 'Téléphone',
  'Occasion', 'Date', 'Début', 'Fin', 'Lieu', 'Personnes', 'Prestations', 'Sono sur place',
  'Éclairage sur place', 'Sélection', 'Estimation (€)', 'Message', 'Agenda', 'Suivi'];
const COL = Object.fromEntries(ENTETES.map((h, i) => [h, i + 1]));
const STATUTS = ['Nouveau', 'Rappelé', 'Devis envoyé', 'Signé', 'Perdu'];

/* ===================== Installation (à exécuter une fois) ===================== */

function installer() {
  if (Session.getScriptTimeZone() !== CONFIG.FUSEAU)
    throw new Error('Réglez le fuseau du projet sur ' + CONFIG.FUSEAU + ' (Paramètres du projet), puis relancez.');
  const props = PropertiesService.getScriptProperties();

  let ss = props.getProperty('TABLEAU_ID') ? SpreadsheetApp.openById(props.getProperty('TABLEAU_ID')) : null;
  if (!ss) {
    ss = SpreadsheetApp.create(CONFIG.TABLEAU_NOM);
    ss.setSpreadsheetTimeZone(CONFIG.FUSEAU);
    props.setProperty('TABLEAU_ID', ss.getId());
  }
  let sh = ss.getSheetByName(CONFIG.ONGLET);
  if (!sh) {
    sh = ss.getSheets()[0].getLastRow() === 0 ? ss.getSheets()[0].setName(CONFIG.ONGLET) : ss.insertSheet(CONFIG.ONGLET);
    sh.appendRow(ENTETES);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, ENTETES.length).setFontWeight('bold').setBackground('#e9d9b4');
    sh.setColumnWidths(1, ENTETES.length, 140);
    sh.setColumnWidths(COL['Sélection'], 1, 320);
    sh.setColumnWidths(COL['Message'], 1, 260);
    sh.getRange(2, COL['Statut'], sh.getMaxRows() - 1, 1).setDataValidation(
      SpreadsheetApp.newDataValidation().requireValueInList(STATUTS, true).build());
  } else if (sh.getRange(1, 1, 1, ENTETES.length).getDisplayValues()[0].join('|') !== ENTETES.join('|')) {
    throw new Error('L’onglet « ' + CONFIG.ONGLET + ' » existe avec d’autres colonnes : rien n’a été modifié.');
  }

  let agenda = props.getProperty('AGENDA_ID') ? CalendarApp.getCalendarById(props.getProperty('AGENDA_ID')) : null;
  if (!agenda) {
    agenda = CalendarApp.createCalendar(CONFIG.AGENDA_NOM, {
      timeZone: CONFIG.FUSEAU, color: CalendarApp.Color.YELLOW,
      summary: 'Demandes reçues via le formulaire de devis de alexisevenementiel.fr'
    });
    props.setProperty('AGENDA_ID', agenda.getId());
  }

  console.log('INSTALLATION OK\nTableau : ' + ss.getUrl() + '\nAgenda : « ' + agenda.getName() + ' » (visible dans Google Agenda)');
  return ss.getUrl();
}

/* ===================== Réception du formulaire ===================== */

function doGet() {
  return json_({ ok: true, service: 'Demandes de devis — ' + CONFIG.NOM });
}

function doPost(e) {
  let a;
  try { a = JSON.parse((e && e.postData && e.postData.contents) || '{}'); }
  catch (err) { return json_({ ok: false, error: 'Requête illisible.' }); }

  // Robots : champ piège rempli, ou formulaire envoyé trop vite. On répond « ok » sans rien enregistrer.
  if (String(a.site_web || '').trim() || (Number(a.delai) > 0 && Number(a.delai) < CONFIG.DELAI_MIN_MS))
    return json_({ ok: true });

  try {
    return json_(enregistrer_(a, false));
  } catch (err) {
    console.error('Demande refusée : ' + (err.message || err));
    return json_({ ok: false, error: String(err.message || err) });
  }
}

function enregistrer_(a, test) {
  const d = valider_(a);
  const props = PropertiesService.getScriptProperties();
  if (!props.getProperty('TABLEAU_ID')) throw new Error('Script non installé : exécuter installer().');

  if (!test) {
    const cache = CacheService.getScriptCache(), k = 'compteur_' + Utilities.formatDate(new Date(), CONFIG.FUSEAU, 'yyyyMMddHH');
    const n = Number(cache.get(k) || 0) + 1;
    if (n > CONFIG.MAX_PAR_HEURE) throw new Error('Trop de demandes en ce moment, merci de réessayer plus tard.');
    cache.put(k, String(n), 3600);
  }

  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  let sh, ligne;
  try {
    sh = SpreadsheetApp.openById(props.getProperty('TABLEAU_ID')).getSheetByName(CONFIG.ONGLET);
    // Même référence déjà reçue (double clic, nouvel essai après coupure) : rien en double.
    if (sh.getLastRow() > 1 && sh.getRange(2, COL['Référence'], sh.getLastRow() - 1, 1)
        .createTextFinder(d.id).matchEntireCell(true).findNext())
      return { ok: true, id: d.id, doublon: true };

    sh.appendRow([new Date(), d.id, test ? 'TEST' : 'Nouveau', d.prenom, d.nom, d.email, d.tel ? "'" + d.tel : '',
      d.occasion, d.date ? dateFr_(d.date) : 'À définir', d.debut, d.fin, d.lieu, d.pers, d.prestations,
      d.son, d.eclairage, d.selection, d.estimation === null ? '' : d.estimation, d.message, '', '']
      .map(sur_));
    ligne = sh.getLastRow();
  } finally { lock.releaseLock(); }

  const suivi = [];
  try {
    const ev = creerEvenement_(d, test, sh.getParent().getUrl());
    sh.getRange(ligne, COL['Agenda']).setValue(ev ? 'Créé' : 'Pas de date');
  } catch (err) { suivi.push('Agenda : ' + (err.message || err)); }
  try {
    notifier_(d, test, sh.getParent().getUrl());
    if (CONFIG.RECAP_CLIENT && !test) recapClient_(d);
  } catch (err) { suivi.push('E-mail : ' + (err.message || err)); }
  sh.getRange(ligne, COL['Suivi']).setValue(suivi.length ? 'ERREUR — ' + suivi.join(' / ') : 'OK');

  return { ok: true, id: d.id };
}

/* ===================== Agenda et e-mails ===================== */

function creerEvenement_(d, test, urlTableau) {
  if (!d.date) return null;
  const agenda = CalendarApp.getCalendarById(PropertiesService.getScriptProperties().getProperty('AGENDA_ID'));
  if (!agenda) throw new Error('agenda « ' + CONFIG.AGENDA_NOM + ' » introuvable (relancer installer()).');

  const titre = (test ? 'TEST — ' : '') + 'Devis · ' + (d.occasion || 'Événement') + ' · ' +
    [d.prenom, d.nom].filter(String).join(' ') + (d.pers ? ' (' + d.pers + ' pers.)' : '');
  const options = { description: resume_(d) + '\n\nTableau des demandes : ' + urlTableau, location: d.lieu, sendInvites: false };

  let ev;
  if (d.debut && d.fin) {
    const debut = Utilities.parseDate(d.date + ' ' + d.debut, CONFIG.FUSEAU, 'yyyy-MM-dd HH:mm');
    let fin = Utilities.parseDate(d.date + ' ' + d.fin, CONFIG.FUSEAU, 'yyyy-MM-dd HH:mm');
    if (fin <= debut) fin = new Date(fin.getTime() + 24 * 3600 * 1000);   // soirée qui finit après minuit
    ev = agenda.createEvent(titre, debut, fin, options);
  } else {
    ev = agenda.createAllDayEvent(titre, Utilities.parseDate(d.date + ' 12:00', CONFIG.FUSEAU, 'yyyy-MM-dd HH:mm'), options);
  }
  ev.setTransparency(CalendarApp.EventTransparency.TRANSPARENT);   // une demande ne bloque pas la journée
  ev.removeAllReminders();
  return ev;
}

function notifier_(d, test, urlTableau) {
  const sujet = (test ? '[TEST] ' : '') + 'Nouvelle demande de devis — ' + [d.prenom, d.nom].filter(String).join(' ') +
    ' — ' + (d.date ? dateFr_(d.date) : 'date à définir');
  MailApp.sendEmail({
    to: CONFIG.NOTIF_EMAIL, replyTo: d.email, name: 'Site ' + CONFIG.NOM,
    subject: sujet.replace(/[\r\n]+/g, ' ').slice(0, 200),
    body: resume_(d) + '\n\n—\nRépondre à ce mail écrit directement au client.\nTableau des demandes : ' + urlTableau +
      (d.date ? '\nL’option est notée dans l’agenda « ' + CONFIG.AGENDA_NOM + ' ».' : '')
  });
}

function recapClient_(d) {
  MailApp.sendEmail({
    to: d.email, replyTo: CONFIG.NOTIF_EMAIL, name: CONFIG.NOM,
    subject: 'Votre demande de devis — ' + CONFIG.NOM,
    body: 'Bonjour ' + d.prenom + ',\n\nMerci pour votre demande, je reviens vers vous très vite avec une proposition.\n\n' +
      'Récapitulatif :\n\n' + resume_(d) + '\n\nÀ bientôt,\nAlexis — ' + CONFIG.NOM + '\n06 18 85 58 92 · alexisevenementiel.fr'
  });
}

function resume_(d) {
  const L = ['=== ÉVÉNEMENT ==='];
  L.push('Occasion : ' + (d.occasion || '—'));
  L.push('Date : ' + (d.date ? dateFr_(d.date) : 'à définir'));
  if (d.debut || d.fin) L.push('Horaires : ' + (d.debut || '?') + ' → ' + (d.fin || '?'));
  if (d.lieu) L.push('Lieu : ' + d.lieu);
  if (d.pers) L.push('Nombre de personnes : ' + d.pers);
  L.push('', '=== BESOINS ===');
  L.push('Prestations souhaitées : ' + (d.prestations || 'à définir'));
  if (d.son) L.push('Sonorisation sur place : ' + d.son);
  if (d.eclairage) L.push('Éclairage sur place : ' + d.eclairage);
  L.push('', '=== SÉLECTION ===', d.selection || '(aucune)');
  L.push('', '=== CONTACT ===', [d.prenom, d.nom].filter(String).join(' '), 'E-mail : ' + d.email);
  if (d.tel) L.push('Téléphone : ' + d.tel);
  if (d.message) L.push('Message : ' + d.message);
  L.push('', 'Référence : ' + d.id);
  return L.join('\n');
}

/* ===================== Outils ===================== */

function valider_(a) {
  const t = (k, max) => {
    const s = String(a[k] == null ? '' : a[k]).trim();
    if (s.length > max) throw new Error('Champ trop long : ' + k);
    return s;
  };
  const d = {
    id: t('id', 100), prenom: t('prenom', 100), nom: t('nom', 100), email: t('email', 200), tel: t('tel', 40),
    occasion: t('occasion', 100), date: t('date', 10), debut: t('debut', 5), fin: t('fin', 5), lieu: t('lieu', 200),
    pers: t('pers', 50), prestations: t('prestations', 300), son: t('son', 50), eclairage: t('eclairage', 50),
    selection: t('selection', 6000), message: t('message', 4000)
  };
  if (!/^[a-zA-Z0-9-]{8,100}$/.test(d.id)) throw new Error('Référence invalide, rechargez la page.');
  if (!d.prenom) throw new Error('Le prénom est obligatoire.');
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(d.email)) throw new Error('Adresse e-mail invalide.');
  if (d.date) {
    const m = d.date.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    const x = m && new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    if (!m || x.getUTCMonth() !== +m[2] - 1 || x.getUTCDate() !== +m[3]) throw new Error('Date invalide.');
  }
  ['debut', 'fin'].forEach(k => { if (d[k] && !/^([01]\d|2[0-3]):[0-5]\d$/.test(d[k])) throw new Error('Heure invalide.'); });
  const est = Number(a.estimation);
  d.estimation = isFinite(est) && est > 0 ? Math.round(est * 100) / 100 : null;
  return d;
}

function dateFr_(iso) { const p = iso.split('-'); return p[2] + '/' + p[1] + '/' + p[0]; }

// Empêche qu'un champ commençant par = + - @ soit interprété comme une formule dans le tableau.
function sur_(v) { return typeof v === 'string' && /^[=+\-@]/.test(v) ? "'" + v : v; }

function json_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }

/* ===================== Test manuel (depuis l'éditeur) ===================== */

/** Crée une demande « TEST » : une ligne dans le tableau, un événement le mois prochain, un e-mail [TEST]. */
function testerDemande() {
  const date = new Date(); date.setMonth(date.getMonth() + 1);
  const r = enregistrer_({
    id: 'test-' + Utilities.getUuid(), prenom: 'Camille', nom: 'Test', email: CONFIG.NOTIF_EMAIL, tel: '06 00 00 00 00',
    occasion: 'Mariage', date: Utilities.formatDate(date, CONFIG.FUSEAU, 'yyyy-MM-dd'), debut: '19:00', fin: '02:00',
    lieu: 'Albi', pers: '100 à 200', prestations: 'DJ / Animateur, Photobooth', son: 'Non, à prévoir', eclairage: 'Non, à prévoir',
    selection: '- Pack Soirée x1 : sur devis\nEstimation à la carte : 0 € (prix pack à définir)', estimation: 0,
    message: 'Demande de test envoyée depuis l’éditeur Apps Script.'
  }, true);
  console.log('TEST OK — référence ' + r.id + '. Vérifiez le tableau, l’agenda « ' + CONFIG.AGENDA_NOM + ' » et vos e-mails.');
}
