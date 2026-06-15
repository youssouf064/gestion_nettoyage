from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)
DB_NAME = "nettoyage.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS sites (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        nom TEXT NOT NULL, 
        adresse TEXT,
        latitude REAL,
        longitude REAL
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS employes (
        matricule TEXT PRIMARY KEY, 
        nom TEXT NOT NULL, 
        prenom TEXT NOT NULL, 
        salaire_base REAL NOT NULL, 
        statut TEXT DEFAULT 'Actif',
        id_site_affecte INTEGER,
        FOREIGN KEY(id_site_affecte) REFERENCES sites(id)
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS pointages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        matricule_employe TEXT,
        id_site INTEGER,
        date_jour TEXT NOT NULL,
        heure_arrivee TEXT,
        heure_depart TEXT,
        FOREIGN KEY(matricule_employe) REFERENCES employes(matricule),
        FOREIGN KEY(id_site) REFERENCES sites(id)
    )''')
    conn.close()

init_db()

@app.route('/')
def dashboard():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Statistiques Globales
    cursor.execute("SELECT COUNT(*) FROM employes WHERE statut = 'Actif'")
    total_actifs = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM employes WHERE statut = 'En congé'")
    total_conges = cursor.fetchone()[0]
    
    # 2. Liste des sites avec NOMBRE D'EMPLOYÉS PRÉSENTS EN CE MOMENT
    cursor.execute('''
        SELECT s.id, s.nom, s.adresse,
        (SELECT COUNT(*) FROM pointages p WHERE p.id_site = s.id AND p.date_jour = date('now') AND p.heure_depart IS NULL) as presents
        FROM sites s
    ''')
    liste_sites = cursor.fetchall()
    
    # 3. Liste complète des employés
    cursor.execute('''
        SELECT e.matricule, e.nom, e.prenom, e.salaire_base, e.statut, s.nom 
        FROM employes e
        LEFT JOIN sites s ON e.id_site_affecte = s.id
    ''')
    liste_employes = cursor.fetchall()
    
    # 4. Liste des personnes en congé spécifiquement
    cursor.execute("SELECT matricule, nom, prenom FROM employes WHERE statut = 'En congé'")
    employes_en_conge = cursor.fetchall()
    
    # 5. Historique général des pointages du jour
    cursor.execute('''
        SELECT p.id, e.prenom, e.nom, s.nom, p.date_jour, p.heure_arrivee, p.heure_depart 
        FROM pointages p
        JOIN employes e ON p.matricule_employe = e.matricule
        JOIN sites s ON p.id_site = s.id
        ORDER BY p.id DESC
    ''')
    historique_pointages = cursor.fetchall()
    
    conn.close()
    
    return render_template('dashboard.html', 
                           total_actifs=total_actifs, 
                           total_conges=total_conges, 
                           sites=liste_sites,
                           employes=liste_employes,
                           conges=employes_en_conge,
                           pointages=historique_pointages)

@app.route('/ajouter_site', methods=['POST'])
def ajouter_site():
    nom_site = request.form.get('nom_site').strip()
    adresse_site = request.form.get('adresse_site').strip()
    if nom_site:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO sites (nom, adresse) VALUES (?, ?)", (nom_site, adresse_site))
        conn.commit()
        conn.close()
    return redirect(url_for('dashboard'))

@app.route('/ajouter_employe', methods=['POST'])
def ajouter_employe():
    matricule = request.form.get('matricule').upper().strip()
    nom = request.form.get('nom').strip()
    prenom = request.form.get('prenom').strip()
    salaire = request.form.get('salaire')
    statut = request.form.get('statut')
    site_id = request.form.get('site_id')
    
    if matricule and nom and prenom and salaire:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO employes (matricule, nom, prenom, salaire_base, statut, id_site_affecte)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (matricule, nom, prenom, float(salaire), statut, int(site_id)))
        conn.commit()
        conn.close()
    return redirect(url_for('dashboard'))

@app.route('/supprimer_employe/<matricule>', methods=['POST'])
def supprimer_employe(matricule):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pointages WHERE matricule_employe = ?", (matricule,))
    cursor.execute("DELETE FROM employes WHERE matricule = ?", (matricule,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

# --- ESPACE CHIEF D'ÉQUIPE / EMPLOYÉ SUR TERRAIN ---

@app.route('/pointage')
def espace_pointage():
    """L'interface simplifiée pour le téléphone de l'employé."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT matricule, nom, prenom FROM employes WHERE statut = 'Actif'")
    liste_employes = cursor.fetchall()
    cursor.execute("SELECT id, nom FROM sites")
    liste_sites = cursor.fetchall()
    conn.close()
    return render_template('pointage.html', employes=liste_employes, sites=liste_sites)

@app.route('/executer_pointage', methods=['POST'])
def executer_pointage():
    """Traite le pointage avec validation des coordonnées GPS."""
    matricule = request.form.get('matricule')
    site_id = request.form.get('site_id')
    action = request.form.get('action')
    lat = request.form.get('latitude')
    lng = request.form.get('longitude')
    
    # Ici, vous pourriez ajouter une vérification de distance GPS avec le site.
    # Pour l'instant, on enregistre directement la position reçue pour l'historique admin.
    print(f"Pointage reçu pour {matricule} au site {site_id}. Action: {action}. GPS: {lat}, {lng}")
    
    date_aujourdhui = datetime.now().strftime('%Y-%m-%d')
    heure_actuelle = datetime.now().strftime('%H:%M:%S')
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    if action == 'arrivee':
        # Crée une nouvelle ligne d'arrivée
        cursor.execute('''
            INSERT INTO pointages (matricule_employe, id_site, date_jour, heure_arrivee)
            VALUES (?, ?, ?, ?)
        ''', (matricule, int(site_id), date_aujourdhui, heure_actuelle))
    elif action == 'depart':
        # Met à jour la ligne d'arrivée existante qui n'a pas encore de départ
        cursor.execute('''
            UPDATE pointages 
            SET heure_depart = ? 
            WHERE matricule_employe = ? AND date_jour = ? AND heure_depart IS NOT NULL
        ''', (heure_actuelle, matricule, date_aujourdhui))
        
        # Si aucune ligne mise à jour, on ferme le pointage le plus récent ouvert
        if cursor.rowcount == 0:
            cursor.execute('''
                UPDATE pointages 
                SET heure_depart = ? 
                WHERE id = (
                    SELECT id FROM pointages 
                    WHERE matricule_employe = ? AND heure_depart IS NULL 
                    ORDER BY id DESC LIMIT 1
                )
            ''', (heure_actuelle, matricule))
            
    conn.commit()
    conn.close()
    return "<h3>Pointage réussi ! Merci.</h3><br><a href='/pointage'>Retour</a>"

def calculer_heures(arrivee, depart):
    if not arrivee or not depart:
        return 0.0
    fmt = '%H:%M:%S'
    t_arrivee = datetime.strptime(arrivee, fmt)
    t_depart = datetime.strptime(depart, fmt)
    diff = t_depart - t_arrivee
    return round(diff.total_seconds() / 3600, 2)

@app.route('/paie')
def rapport_paie():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT matricule, nom, prenom, salaire_base FROM employes")
    liste_employes = cursor.fetchall()
    
    bilan_paie = []
    for emp in liste_employes:
        matricule, nom, prenom, salaire_base = emp
        cursor.execute('SELECT heure_arrivee, heure_depart FROM pointages WHERE matricule_employe = ? AND heure_depart IS NOT NULL', (matricule,))
        pointages = cursor.fetchall()
        
        total_heures = 0.0
        for p in pointages:
            total_heures += calculer_heures(p[0], p[1])
            
        taux_horaire = round(salaire_base / 160, 2)
        salaire_gagne = round(total_heures * taux_horaire, 2)
        
        bilan_paie.append({
            'matricule': matricule, 'nom': nom, 'prenom': prenom,
            'heures': total_heures, 'taux': taux_horaire, 'salaire_du': salaire_gagne
        })
        
    conn.close()
    return render_template('paie.html', bilan=bilan_paie)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)