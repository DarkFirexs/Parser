#!/usr/bin/env python3
"""
ИДЕАЛЬНЫЙ ПАРСЕР - КАЧЕСТВО > КОЛИЧЕСТВО
Строгий отбор: только лучшие конфиги для обхода белых списков
"""

import requests
import base64
import socket
import json
import re
from datetime import datetime
from urllib.parse import unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# ==================== КОНФИГУРАЦИЯ ====================

SOURCES = [
    'https://raw.githubusercontent.com/whoahaow/rjsxrd/refs/heads/main/githubmirror/bypass/bypass-all.txt',
    'https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/WHITE-CIDR-RU-all.txt',
    'https://raw.githubusercontent.com/zieng2/wl/main/vless_lite.txt',
    'https://raw.githubusercontent.com/AvenCores/goida-vpn-configs/refs/heads/main/githubmirror/26.txt',
]

# КРИТИЧНЫЕ российские SNI домены
WHITELIST_SNI = [
    'yandex.ru', 'ya.ru', 'vk.com', 'mail.ru', 'login.vk.com',
    'sberbank.ru', 'cdn.tbank.ru', 'ozon.ru', 'wildberries.ru',
    'avito.st', 'gosuslugi.ru', 'max.ru', 'web.max.ru',
    'speedload.ru', 'ign.com', 'ign.dev', 'snowfall.top',
    'userapi.com', 'rutube.ru', 'ok.ru', 'dzen.ru'
]

# Лучшие транспорты (стабильные)
BEST_TRANSPORTS = ['xhttp', 'grpc', 'ws']

# ==================== ПАРСЕР ====================

class StrictParser:
    """СТРОГИЙ парсер - только VLESS+Reality"""
    
    def parse_vless(self, config):
        try:
            config_clean = config.replace('vless://', '')
            parts = config_clean.split('#')[0].split('?')[0]
            uuid_and_server = parts.split('@')
            
            if len(uuid_and_server) < 2:
                return None
            
            uuid = uuid_and_server[0]
            server_port = uuid_and_server[1]
            server, port = server_port.rsplit(':', 1)
            
            # Извлекаем параметры
            sni = self.extract_param(config, 'sni')
            security = self.extract_param(config, 'security')
            transport = self.extract_param(config, 'type')
            flow = self.extract_param(config, 'flow')
            
            return {
                'type': 'vless',
                'uuid': uuid,
                'server': server,
                'port': int(port),
                'sni': sni,
                'security': security,
                'transport': transport or 'tcp',
                'flow': flow,
                'raw': config
            }
        except:
            return None
    
    def extract_param(self, config, param):
        """Извлечь параметр из URL"""
        patterns = [
            rf'{param}=([^&\s#]+)',
            rf'{param}:([^&\s#]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, config, re.IGNORECASE)
            if match:
                return unquote(match.group(1))
        return None
    
    def parse_config(self, config):
        """ТОЛЬКО VLESS"""
        if config.startswith('vless://'):
            return self.parse_vless(config)
        return None


class StrictDeduplicator:
    """Умное удаление дублей"""
    
    @staticmethod
    def get_key(config, parsed):
        """UUID + Server + Port"""
        return f"{parsed['uuid']}@{parsed['server']}:{parsed['port']}"
    
    @staticmethod
    def deduplicate(configs, parser):
        seen = {}
        unique = []
        
        for config in configs:
            parsed = parser.parse_config(config)
            if not parsed:
                continue
            
            key = StrictDeduplicator.get_key(config, parsed)
            
            if key not in seen:
                seen[key] = config
                unique.append(config)
        
        return unique, len(configs) - len(unique)


class StrictChecker:
    """ЖЁСТКАЯ проверка качества"""
    
    def __init__(self):
        self.checked = 0
    
    def is_whitelist_sni(self, sni):
        """SNI должен быть российским"""
        if not sni:
            return False
        sni_lower = sni.lower()
        return any(domain in sni_lower for domain in WHITELIST_SNI)
    
    def check_ping(self, server, port, timeout=3):
        """TCP пинг"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((server, port))
            sock.close()
            return result == 0
        except:
            return False
    
    def get_country(self, ip):
        """Страна сервера"""
        try:
            r = requests.get(f'http://ip-api.com/json/{ip}?fields=country,countryCode', timeout=5)
            data = r.json()
            return data.get('countryCode', 'XX')
        except:
            return 'XX'
    
    def calculate_score(self, parsed):
        """Система оценки качества"""
        score = 0
        
        # Reality = +50
        if parsed.get('security') == 'reality':
            score += 50
        
        # SNI bypass = +30
        if self.is_whitelist_sni(parsed.get('sni')):
            score += 30
        
        # Хороший транспорт = +20
        if parsed.get('transport') in BEST_TRANSPORTS:
            score += 20
        
        # Flow xtls-rprx-vision = +10
        if 'vision' in (parsed.get('flow') or '').lower():
            score += 10
        
        return score
    
    def check_config(self, config, parser):
        """СТРОГАЯ проверка"""
        parsed = parser.parse_config(config)
        
        if not parsed:
            return None
        
        # 1. ТОЛЬКО VLESS
        if parsed['type'] != 'vless':
            return None
        
        # 2. ТОЛЬКО Reality
        if parsed.get('security') != 'reality':
            return None
        
        # 3. ОБЯЗАТЕЛЬНО SNI российский
        if not self.is_whitelist_sni(parsed.get('sni')):
            return None
        
        # 4. Предпочтение хорошим транспортам (не обязательно)
        transport = parsed.get('transport', 'tcp')
        
        # 5. Проверка доступности
        if not self.check_ping(parsed['server'], parsed['port']):
            return None
        
        # 6. Страна
        country = self.get_country(parsed['server'])
        parsed['country'] = country
        
        # 7. Оценка качества
        score = self.calculate_score(parsed)
        parsed['quality_score'] = score
        parsed['transport'] = transport
        
        self.checked += 1
        if self.checked % 50 == 0:
            print(f"  ✅ Проверено: {self.checked}")
        
        return parsed


# ==================== ОСНОВНАЯ ЛОГИКА ====================

def collect_configs():
    """Сбор"""
    print("📡 Сбор конфигов...")
    print("-" * 70)
    
    all_configs = []
    
    for url in SOURCES:
        try:
            print(f"  {url.split('/')[-1]}")
            r = requests.get(url, timeout=15)
            
            try:
                decoded = base64.b64decode(r.text).decode('utf-8')
                configs = decoded.strip().split('\n')
            except:
                configs = r.text.strip().split('\n')
            
            # Только VLESS
            vless = [c.strip() for c in configs if c.strip().startswith('vless://')]
            all_configs.extend(vless)
            print(f"    ✅ VLESS: {len(vless)}")
            
        except Exception as e:
            print(f"    ❌ {e}")
    
    print(f"\n📊 VLESS собрано: {len(all_configs)}")
    return all_configs


def main():
    print("\n" + "=" * 70)
    print("🔥 ИДЕАЛЬНЫЙ ПАРСЕР - КАЧЕСТВО > КОЛИЧЕСТВО")
    print("=" * 70)
    
    start = time.time()
    
    # Шаг 1: Сбор
    all_configs = collect_configs()
    
    # Шаг 2: Дедупликация
    print("\n🔄 Удаление дублей...")
    print("-" * 70)
    
    parser = StrictParser()
    unique, dupes = StrictDeduplicator.deduplicate(all_configs, parser)
    
    print(f"  Удалено: {dupes}")
    print(f"  Уникальных: {len(unique)}")
    
    # Шаг 3: ЖЁСТКАЯ фильтрация
    print(f"\n✅ СТРОГАЯ проверка (Reality + SNI + Ping)...")
    print("⏰ Это займёт время...")
    print("-" * 70)
    
    checker = StrictChecker()
    valid = []
    
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(checker.check_config, cfg, parser): cfg 
                   for cfg in unique}
        
        for future in as_completed(futures):
            result = future.result()
            if result:
                valid.append(result)
    
    # Сортировка по качеству
    valid.sort(key=lambda x: x.get('quality_score', 0), reverse=True)
    
    elapsed = time.time() - start
    
    # Статистика
    print(f"\n📊 РЕЗУЛЬТАТЫ:")
    print("=" * 70)
    print(f"⏱️  Время: {elapsed/60:.1f} мин")
    print(f"📥 Собрано VLESS: {len(all_configs)}")
    print(f"🔄 Дублей удалено: {dupes}")
    print(f"🎯 Уникальных: {len(unique)}")
    print(f"✅ ИДЕАЛЬНЫХ: {len(valid)}")
    print(f"❌ Отфильтровано: {len(unique) - len(valid)}")
    print(f"📈 Процент прошедших: {len(valid)/len(unique)*100:.1f}%")
    
    # Группировка
    transports = {}
    countries = {}
    scores = []
    
    for cfg in valid:
        t = cfg.get('transport', 'tcp')
        transports[t] = transports.get(t, 0) + 1
        
        c = cfg.get('country', 'XX')
        countries[c] = countries.get(c, 0) + 1
        
        scores.append(cfg.get('quality_score', 0))
    
    print(f"\n🚀 По транспортам:")
    for t, count in sorted(transports.items(), key=lambda x: x[1], reverse=True):
        print(f"  {t}: {count}")
    
    print(f"\n🌍 По странам (топ-10):")
    for c, count in sorted(countries.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {c}: {count}")
    
    if scores:
        avg_score = sum(scores) / len(scores)
        print(f"\n⭐ Средний score качества: {avg_score:.1f}/110")
    
    # Сохранение
    print(f"\n💾 Сохранение...")
    print("-" * 70)
    
    raw_all = [c['raw'] for c in valid]
    
    # Все идеальные
    with open('configs.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(raw_all))
    
    with open('configs_b64.txt', 'w', encoding='utf-8') as f:
        f.write(base64.b64encode('\n'.join(raw_all).encode()).decode())
    
    print(f"  ✅ configs.txt ({len(valid)} идеальных)")
    print(f"  ✅ configs_b64.txt (для подписки)")
    
    # Топ-100 по score
    if len(valid) > 100:
        top100 = valid[:100]
        top100_raw = [c['raw'] for c in top100]
        
        with open('configs_top100.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(top100_raw))
        
        with open('configs_top100_b64.txt', 'w', encoding='utf-8') as f:
            f.write(base64.b64encode('\n'.join(top100_raw).encode()).decode())
        
        print(f"  ✅ configs_top100.txt (лучшие из лучших)")
        print(f"  ✅ configs_top100_b64.txt")
    
    # Статистика
    stats = {
        'timestamp': datetime.now().isoformat(),
        'duration_minutes': round(elapsed / 60, 2),
        'collected_vless': len(all_configs),
        'duplicates_removed': dupes,
        'unique': len(unique),
        'perfect_configs': len(valid),
        'filtered_out': len(unique) - len(valid),
        'pass_rate': round((len(valid) / len(unique)) * 100, 2),
        'avg_quality_score': round(sum(scores) / len(scores), 2) if scores else 0,
        'transports': transports,
        'countries': countries,
        'criteria': {
            'protocol': 'VLESS только',
            'security': 'Reality обязательно',
            'sni': 'Российские домены',
            'check': 'Ping доступности',
            'quality_score': 'Система оценок'
        }
    }
    
    with open('stats.json', 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    
    print(f"  ✅ stats.json")
    
    print(f"\n🎉 ГОТОВО! {len(valid)} ИДЕАЛЬНЫХ конфигов")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70 + "\n")


if __name__ == '__main__':
    main()
