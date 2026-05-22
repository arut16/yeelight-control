#!/usr/bin/env python3

import subprocess
import json
import logging
import os
from datetime import datetime

# Configuration des logs
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, 'Config')
LOGS_DIR = os.path.join(BASE_DIR, 'Logs')

logging.basicConfig(filename=os.path.join(LOGS_DIR, 'lamp_ips_update.log'), level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# --- DÉBUT DE LA LOGIQUE INTELLIGENTE ---

# 1. On définit d'abord les valeurs par défaut (Hardcoded) comme filet de sécurité
DEFAULT_MAC_TO_NAME = {
    "50:EC:50:81:B1:1C": "Chambre",
    "50:EC:50:82:99:BF": "Chambre David",
    "50:EC:50:82:A7:14": "Bureau",
    "B4:60:ED:2D:FF:4F": "Bureau David",
    "04:CF:8C:B3:C4:BF": "Salon",
    "54:48:E6:5E:18:EC": "Cuisine",
    "54:48:E6:78:AF:6C": "Salle de Bain"
}

# 2. On essaie de charger la configuration dynamique depuis lamp_config.json
try:
    with open(os.path.join(CONFIG_DIR, 'lamp_config.json'), 'r') as f:
        config = json.load(f)
        # On inverse la logique du JSON qui est souvent Nom -> MAC ou l'inverse
        # Votre JSON est : "MAC": "Nom" (comme dans le code python)
        MAC_TO_NAME = config.get("lampes", {})
        
        # Si le JSON est vide ou mal formé, on force une erreur pour utiliser le backup
        if not MAC_TO_NAME:
            raise ValueError("JSON vide ou clé 'lampes' manquante")
            
        logging.info("Configuration chargée depuis lamp_config.json")

except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
    logging.warning(f"Impossible de lire lamp_config.json ({e}). Utilisation des valeurs par défaut.")
    # C'est ici qu'on utilise le filet de sécurité au lieu de listes vides !
    MAC_TO_NAME = DEFAULT_MAC_TO_NAME

# 3. On définit l'ordre désiré basé sur la liste (JSON ou Défaut)
DESIRED_ORDER = list(MAC_TO_NAME.values())

# --- FIN DE LA LOGIQUE INTELLIGENTE ---

def load_existing_lamp_ips():
    """Charge les IPs actuelles depuis lamp_ips.json, ou retourne un dictionnaire vide si le fichier n'existe pas."""
    try:
        with open(os.path.join(CONFIG_DIR, 'lamp_ips.json'), 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logging.warning("lamp_ips.json non trouvé ou invalide. Démarrage avec un dictionnaire vide.")
        return {}

def get_lamp_ips():
    # Charger les IPs actuelles depuis le fichier existant
    lamp_ips = load_existing_lamp_ips()
    detected_macs = set()  # Suivre les MAC détectées pour éviter les doublons
    
    try:
        # Exécute arp-scan avec sudo pour scanner le réseau local
        result = subprocess.run(['sudo', 'arp-scan', '--localnet'], capture_output=True, text=True, check=True, timeout=20)
        arp_output = result.stdout.strip().split('\n')
        
        # Parse les résultats pour extraire IP et MAC, et associer aux noms
        for line in arp_output[2:]:  # Ignorer les lignes d’en-tête
            if line:  # Ignorer les lignes vides
                parts = line.split('\t')
                if len(parts) >= 2:
                    ip = parts[0].strip()
                    mac = parts[1].strip().upper()
                    
                    # C'est ici que MAC_TO_NAME (chargé dynamiquement) est utilisé
                    if mac in MAC_TO_NAME and mac not in detected_macs:
                        name = MAC_TO_NAME[mac]
                        # Mettre à jour uniquement si l'IP a changé
                        if name in lamp_ips:
                            if lamp_ips[name] != ip:
                                logging.info(f"IP de {name} mise à jour : {lamp_ips[name]} → {ip}")
                                lamp_ips[name] = ip
                            else:
                                logging.debug(f"IP de {name} inchangée : {ip}")
                        else:
                            logging.info(f"Nouvelle lampe détectée : {name} avec IP {ip}")
                            lamp_ips[name] = ip
                        detected_macs.add(mac)
        
        # Créer un nouveau dictionnaire avec l’ordre souhaité
        # Note : On filtre pour ne garder que les lampes qui ont bien une IP détectée
        ordered_lamp_ips = {name: lamp_ips.get(name) for name in DESIRED_ORDER if name in lamp_ips}
        
        # Sauvegarder le dictionnaire ordonné dans lamp_ips.json
        with open(os.path.join(CONFIG_DIR, 'lamp_ips.json'), 'w') as f:
            json.dump(ordered_lamp_ips, f, indent=4)
        
        logging.info(f"Table des IPs des lampes mise à jour à {datetime.now()} avec l’ordre : {list(ordered_lamp_ips.keys())}")
    except subprocess.TimeoutExpired:
        logging.error("arp-scan a dépassé le délai d'exécution (20s)")
    except subprocess.CalledProcessError as e:
        logging.error(f"Erreur lors de l'exécution de arp-scan : {e}")
        logging.error(f"Sortie d'erreur arp-scan : {result.stderr}")
    except Exception as e:
        logging.error(f"Erreur inattendue lors de la mise à jour des IPs : {e}")

if __name__ == "__main__":
    get_lamp_ips()