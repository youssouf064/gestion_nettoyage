import csv
import io
from flask import Response
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify, session

app = Flask(__name__)
app.secret_key = "cle_secrete_super_securisee_youssouf"

# --- CONFIGURATION HYBRIDE (NEON SUR RENDER / MYSQL EN LOCAL) ---
IS_RENDER = 'RENDER' in os.environ

if IS_RENDER:
    # Si on est sur Render -> On utilise PostgreSQL (Neon)
    import psycopg2
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    # Si on est sur le Chromebook -> On utilise MySQL/MariaDB local
    import mysql.connector
    DB_CONFIG_LOCAL = {
        'host': 'localhost',
        'user': 'root',
        'password': 'root',
        'database': 'gestion_nettoyage'
    }

def get_db_connection():
    if IS_RENDER:
        # Connexion PostgreSQL pour Neon (Render)
        return psycopg2.connect(DATABASE_URL)
    else:
        # Connexion MySQL pour le Chromebook
        return mysql.connector.connect(**DB_CONFIG_LOCAL)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Adaptations de requêtes selon la base de données détectée
    if IS_RENDER:
        # Syntaxe PostgreSQL pour Neon
        cursor.execute('''CREATE TABLE IF NOT EXISTS sites (
            id SERIAL PRIMARY KEY, 
            nom VARCHAR(255) NOT NULL, 
            adresse VARCHAR(255),
            latitude REAL,
            longitude REAL
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS employes (
            matricule VARCHAR(100) PRIMARY KEY, 
            nom VARCHAR(255) NOT NULL, 
            prenom VARCHAR(255) NOT NULL, 
            salaire_base REAL NOT NULL, 
            statut VARCHAR(50) DEFAULT 'Actif',
            id_site_affecte INT,
            FOREIGN KEY(id_site_affecte) REFERENCES sites(id) ON DELETE SET NULL
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS pointages (
            id SERIAL PRIMARY KEY,
            matricule_employe VARCHAR(100),
            id_site INT,
            date_jour VARCHAR(50) NOT NULL,
            heure_arrivee VARCHAR(50),
            heure_depart VARCHAR(50),
            FOREIGN KEY(matricule_employe) REFERENCES employes(matricule) ON DELETE CASCADE,
            FOREIGN KEY(id_site) REFERENCES sites(id) ON DELETE CASCADE
        )''')
    else:
        # Syntaxe MySQL pour ton Chromebook
        cursor.execute('''CREATE TABLE IF NOT EXISTS sites (
            id INT AUTO_INCREMENT PRIMARY KEY, 
            nom VARCHAR(255) NOT NULL, 
            adresse VARCHAR(255),
            latitude REAL,
            longitude REAL
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS employes (
            matricule VARCHAR(100) PRIMARY KEY, 
            nom VARCHAR(255) NOT NULL, 
            prenom VARCHAR(255) NOT NULL, 
            salaire_base REAL NOT NULL, 
            statut VARCHAR(50) DEFAULT 'Actif',
            id_site_affecte INT,
            FOREIGN KEY(id_site_affecte) REFERENCES sites(id) ON DELETE SET NULL
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS pointages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            matricule_employe VARCHAR(100),
            id_site INT,
            date_jour VARCHAR(50) NOT NULL,
            heure_arrivee VARCHAR(50),
            heure_depart VARCHAR(50),
            FOREIGN KEY(matricule_employe) REFERENCES employes(matricule) ON DELETE CASCADE,
            FOREIGN KEY(id_site) REFERENCES sites(id) ON DELETE CASCADE
        )''')
        
    conn.commit()
    cursor.close()
    conn.close()

# Lance l'initialisation au démarrage
init_db()

# Le code secret que seule la direction doit connaître
CODE_SECRET_ADMIN = "1234"

# --- ACCÈS ET CONTRÔLE DU BUREAU PRINCIPAL ---

@app.route('/', methods=['GET', 'POST'])
def dashboard():
    if request.method == 'POST':
        code_saisi = request.form.get('code_admin')
        if code_saisi == CODE_SECRET_ADMIN:
            session['est_admin'] = True  
        else:
            return render_template('connexion_admin.html', erreur="Code incorrect. Accès refusé.")

    if not session.get('est_admin'):
        return render_template('connexion_admin.html', erreur=None)

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Statistiques Globales
    cursor.execute("SELECT COUNT(*) FROM employes WHERE statut = 'Actif'")
    total_actifs = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM employes WHERE statut = 'En congé'")
    total_conges = cursor.fetchone()[0]
    
    # 2. Liste des sites avec nombre de présents (Correction stricte du type pour PostgreSQL vs MySQL)
    if IS_RENDER:
        fonction_date = "CURRENT_DATE::text"
    else:
        fonction_date = "CURDATE()"

    cursor.execute(f'''
        SELECT s.id, s.nom, s.adresse,
        (SELECT COUNT(*) FROM pointages p WHERE p.id_site = s.id AND p.date_jour = {fonction_date} AND p.heure_depart IS NULL) as presents
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
    
    # 5. Historique général des pointages du jour (avec coordonnées GPS)
    cursor.execute('''
        SELECT p.id, e.prenom, e.nom, s.nom, p.date_jour, p.heure_arrivee, p.heure_depart, p.latitude, p.longitude 
        FROM pointages p
        JOIN employes e ON p.matricule_employe = e.matricule
        JOIN sites s ON p.id_site = s.id
        ORDER BY p.id DESC
    ''')
    historique_pointages = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('dashboard.html', 
                           total_actifs=total_actifs, 
                           total_conges=total_conges, 
                           sites=liste_sites,
                           employes=liste_employes,
                           conges=employes_en_conge,
                           pointages=historique_pointages)


@app.route('/deconnexion')
def deconnexion():
    session.pop('est_admin', None)
    return redirect(url_for('espace_pointage'))


# --- SÉCURISATION DES ACTIONS ADMINISTRATIVE ---

@app.route('/ajouter_site', methods=['POST'])
def ajouter_site():
    if not session.get('est_admin'):
        return redirect(url_for('espace_pointage'))

    nom_site = request.form.get('nom_site').strip()
    adresse_site = request.form.get('adresse_site').strip()
    if nom_site:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO sites (nom, adresse) VALUES (%s, %s)", (nom_site, adresse_site))
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for('dashboard'))


@app.route('/ajouter_employe', methods=['POST'])
def ajouter_employe():
    if not session.get('est_admin'):
        return redirect(url_for('espace_pointage'))

    matricule = request.form.get('matricule').upper().strip()
    nom = request.form.get('nom').strip()
    prenom = request.form.get('prenom').strip()
    salaire = request.form.get('salaire')
    statut = request.form.get('statut')
    site_id = request.form.get('site_id')
    
    if matricule and nom and prenom and salaire:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO employes (matricule, nom, prenom, salaire_base, statut, id_site_affecte)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (matricule, nom, prenom, float(salaire), statut, int(site_id)))
        conn.commit()
        cursor.close()
        conn.close()
    return redirect(url_for('dashboard'))


@app.route('/supprimer_employe/<matricule>', methods=['POST'])
def supprimer_employe(matricule):
    if not session.get('est_admin'):
        return redirect(url_for('espace_pointage'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pointages WHERE matricule_employe = %s", (matricule,))
    cursor.execute("DELETE FROM employes WHERE matricule = %s", (matricule,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('dashboard'))


@app.route('/paie')
def rapport_paie():
    if not session.get('est_admin'):
        return redirect(url_for('espace_pointage'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT matricule, nom, prenom, salaire_base FROM employes")
    liste_employes = cursor.fetchall()
    
    bilan_paie = []
    for emp in liste_employes:
        matricule, nom, prenom, salaire_base = emp
        cursor.execute('SELECT heure_arrivee, heure_depart FROM pointages WHERE matricule_employe = %s AND heure_depart IS NOT NULL', (matricule,))
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
        
    cursor.close()
    conn.close()
    return render_template('paie.html', bilan=bilan_paie)

@app.route('/exporter_paie_csv')
def exporter_paie_csv():
    if not session.get('est_admin'):
        return redirect(url_for('espace_pointage'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT matricule, nom, prenom, salaire_base FROM employes")
    liste_employes = cursor.fetchall()
    
    # Préparation du fichier CSV en mémoire
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';') # Point-virgule idéal pour Excel France/Afrique
    
    # En-tête du tableau Excel
    writer.writerow(['Matricule', 'Employe', 'Total Heures', 'Taux Horaire (MRU/h)', 'Salaire a Verser (MRU)'])
    
    # Reprise exacte des calculs de ta fonction /paie
    for emp in liste_employes:
        matricule, nom, prenom, salaire_base = emp
        cursor.execute('SELECT heure_arrivee, heure_depart FROM pointages WHERE matricule_employe = %s AND heure_depart IS NOT NULL', (matricule,))
        pointages = cursor.fetchall()
        
        total_heures = 0.0
        for p in pointages:
            total_heures += calculer_heures(p[0], p[1])
            
        taux_horaire = round(salaire_base / 160, 2)
        salaire_gagne = round(total_heures * taux_horaire, 2)
        
        # On écrit la ligne de l'employé dans le fichier
        nom_complet = f"{prenom} {nom}"
        writer.writerow([matricule, nom_complet, f"{total_heures} h", f"{taux_horaire} MRU", f"{salaire_gagne} MRU"])
        
    cursor.close()
    conn.close()
    
    # Envoi du fichier au navigateur pour déclencher le téléchargement automatique
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=Rapport_Paie_Nettoyage.csv"}
    )

@app.route('/supprimer_site/<int:id>', methods=['POST'])
def supprimer_site(id):
    if not session.get('est_admin'):
        return redirect(url_for('espace_pointage'))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM pointages WHERE id_site = %s", (id,))
        cursor.execute("DELETE FROM sites WHERE id = %s", (id,))
        conn.commit()
    except Exception as e:
        print(f"Erreur lors de la suppression : {e}")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('dashboard'))


@app.route('/modifier_site/<int:id>', methods=['GET', 'POST'])
def modifier_site(id):
    if not session.get('est_admin'):
        return redirect(url_for('espace_pointage'))

    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        nouveau_nom = request.form.get('nom_site')
        nouvelle_adresse = request.form.get('adresse') or request.form.get('adresse_site')
        
        cursor.execute("UPDATE sites SET nom = %s, adresse = %s WHERE id = %s", 
                       (nouveau_nom, nouvelle_adresse, id))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('dashboard'))
    
    cursor.execute("SELECT id, nom, adresse FROM sites WHERE id = %s", (id,))
    site_data = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not site_data:
        return redirect(url_for('dashboard'))
        
    site = {'id': site_data[0], 'nom_site': site_data[1], 'adresse': site_data[2]}
    return render_template('modifier_site.html', site=site)


# --- ESPACE CHEF D'ÉQUIPE (LIBRE D'ACCÈS) ---

@app.route('/pointage')
def espace_pointage():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT matricule, nom, prenom FROM employes WHERE statut = 'Actif'")
    liste_employes = cursor.fetchall()
    cursor.execute("SELECT id, nom FROM sites")
    liste_sites = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('pointage.html', employes=liste_employes, sites=liste_sites)


@app.route('/executer_pointage', methods=['POST'])
def executer_pointage():
    matricule = request.form.get('matricule')
    site_id = request.form.get('site_id')
    action = request.form.get('action')
    lat = request.form.get('latitude')
    lng = request.form.get('longitude')

    print(f"Pointage reçu pour {matricule} au site {site_id}. Action: {action}. GPS: {lat}, {lng}")
    
    date_aujourdhui = datetime.now().strftime('%Y-%m-%d')
    heure_actuelle = datetime.now().strftime('%H:%M:%S')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # ATTENTION À L'ALIGNEMENT ICI : 4 espaces pour le "if"
    if action == 'arrivee':
        # 8 espaces pour le contenu du "if"
        cursor.execute('''
            INSERT INTO pointages (matricule_employe, id_site, date_jour, heure_arrivee, latitude, longitude)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (matricule, int(site_id), date_aujourdhui, heure_actuelle, lat, lng))

    elif action == 'depart':
        # Le reste de ton code existant pour le départ...
        cursor.execute('''
            UPDATE pointages 
            SET heure_depart = %s 
            WHERE matricule_employe = %s AND date_jour = %s AND heure_depart IS NOT NULL
        ''', (heure_actuelle, matricule, date_aujourdhui))
        # ... (conserve la suite de ton code actuel pour le départ)
        
        if cursor.rowcount == 0:
            if IS_RENDER:
                cursor.execute('''
                    UPDATE pointages 
                    SET heure_depart = %s 
                    WHERE matricule_employe = %s AND heure_depart IS NULL
                ''', (heure_actuelle, matricule))
            else:
                cursor.execute('''
                    UPDATE pointages 
                    SET heure_depart = %s 
                    WHERE id = (
                        SELECT id FROM (
                            SELECT id FROM pointages 
                            WHERE matricule_employe = %s AND heure_depart IS NULL 
                            ORDER BY id DESC LIMIT 1
                        ) as t
                    )
                ''', (heure_actuelle, matricule))
            
    conn.commit()
    cursor.close()
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)