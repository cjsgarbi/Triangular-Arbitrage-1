from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import asyncio
from decimal import Decimal
from ..utils.logger import Logger
import logging


@dataclass
class Symbol:
    base: str
    quote: str

    def __str__(self):
        return f"{self.base}/{self.quote}"


@dataclass
class Ticker:
    symbol: Symbol
    last_price: float
    bid_price: float
    ask_price: float
    bid_qty: float
    ask_qty: float
    volume: float
    trades: int
    timestamp: int
    flipped: bool = False
    rate: float = 0.0

    def get_trade_info(self):
        return {
            'symbol': f"{self.symbol.base}{self.symbol.quote}",
            'side': 'SELL' if self.flipped else 'BUY',
            'type': 'MARKET',
            'quantity': 1
        }


class CurrencyCore:
    def __init__(self, exchange, config):
        self.logger = logging.getLogger(__name__)
        self.exchange = exchange
        self.config = config
        self.tickers = {}
        self.markets = {}
        self.last_update = None
        self.simulation_mode = config.get('SIMULATION_MODE', False)

        # Configuração inicial
        self.logger.info("🔄 Iniciando CurrencyCore...")
        if not self.simulation_mode:
            self.logger.info(
                f"📡 Conectando à {'Binance Testnet' if self.config.get('SIMULATION_MODE') else 'Binance'}")
            self.logger.info(
                f"🔑 Usando API Key: {self.config.get('BINANCE_API_KEY', '')[:8]}...")

    async def initialize(self):
        """Inicializa conexão com a Binance"""
        if self.simulation_mode:
            self.logger.info("✅ Modo simulação - Sem conexão com Binance")
            return

        try:
            # Testa conexão
            self.logger.info("🔍 Testando conexão com Binance...")
            account = await self.exchange.get_account()

            # Log detalhado do resultado
            if account:
                self.logger.info(
                    "✅ Conexão com Binance estabelecida com sucesso!")
                balances = {asset['asset']: float(
                    asset['free']) for asset in account['balances'] if float(asset['free']) > 0}
                self.logger.info(
                    f"💰 Saldo total em BTC: {balances.get('BTC', 0)}")
                self.logger.info(
                    f"📊 Total de moedas com saldo: {len(balances)}")
            else:
                self.logger.warning(
                    "⚠️ Conexão estabelecida mas sem dados de conta")

        except Exception as e:
            self.logger.error(f"❌ Erro ao conectar com Binance: {str(e)}")
            self.logger.error(
                "⚠️ Verifique suas credenciais e conexão com internet")
            self.logger.error(
                f"🔍 Detalhes do erro: {str(e.__class__.__name__)}")
            raise

    async def start_ticker_stream(self):
        """Inicia stream de tickers"""
        if self.simulation_mode:
            self.logger.info("✅ Modo simulação - Usando dados simulados")
            return

        self.logger.info("📊 Iniciando stream de tickers...")
        try:
            # Busca tickers iniciais
            self.logger.info("🔄 Buscando tickers iniciais...")
            tickers = await self.exchange.get_ticker()

            if not tickers:
                self.logger.warning(
                    "⚠️ Nenhum ticker recebido na inicialização")
                return

            self.logger.info(f"✅ {len(tickers)} pares obtidos com sucesso")

            # Processa tickers iniciais
            processed = 0
            for ticker in tickers:
                try:
                    await self.tick(ticker['symbol'], ticker)
                    processed += 1
                except Exception as e:
                    self.logger.debug(f"Erro ao processar ticker: {e}")
                    continue

            self.logger.info(f"✅ {processed} tickers processados com sucesso")

            # Inicia loop de atualização
            asyncio.create_task(self.ticker_loop())

        except Exception as e:
            self.logger.error(f"❌ Erro ao iniciar stream: {str(e)}")
            if self.config.get('DEBUG', False):
                self.logger.error(f"🔍 Detalhes: {str(e.__class__.__name__)}")
            raise

    async def ticker_loop(self, interval=1):
        """Loop principal de atualização de tickers"""
        if self.simulation_mode:
            return

        while True:
            try:
                tickers = await self.exchange.get_ticker()

                if not tickers:
                    self.logger.warning("⚠️ Nenhum ticker recebido da Binance")
                    await asyncio.sleep(interval)
                    continue

                # Atualiza tickers
                updated = 0
                for ticker in tickers:
                    try:
                        await self.tick(ticker['symbol'], ticker)
                        updated += 1
                    except Exception as e:
                        self.logger.debug(
                            f"Erro ao atualizar ticker {ticker['symbol']}: {e}")
                        continue

                self.logger.debug(f"✅ {updated} tickers atualizados")
                await asyncio.sleep(interval)

            except Exception as e:
                self.logger.error(f"❌ Erro no loop de tickers: {str(e)}")
                if self.config.get('DEBUG', False):
                    self.logger.error(
                        f"🔍 Detalhes: {str(e.__class__.__name__)}")
                await asyncio.sleep(interval)

    async def tick(self, symbol, ticker):
        """Processa um tick do mercado"""
        try:
            # Extrai base e quote do symbol (ex: BTCUSDT -> BTC/USDT)
            # Identifica pares comuns de quote
            quotes = ['USDT', 'BTC', 'ETH', 'BNB', 'BUSD', 'USDC']
            quote = None
            base = None

            # Encontra a quote correta
            for q in quotes:
                if symbol.endswith(q):
                    quote = q
                    base = symbol[:-len(q)]
                    break

            if not quote or not base:
                self.logger.warning(
                    f"❌ Não foi possível identificar base/quote para {symbol}")
                return

            ticker_obj = Ticker(
                symbol=Symbol(base=base, quote=quote),
                last_price=float(ticker.get(
                    'lastPrice', ticker.get('price', 0))),
                bid_price=float(ticker.get(
                    'bidPrice', ticker.get('price', 0))),
                ask_price=float(ticker.get(
                    'askPrice', ticker.get('price', 0))),
                bid_qty=float(ticker.get('bidQty', 0)),
                ask_qty=float(ticker.get('askQty', 0)),
                volume=float(ticker.get(
                    'volume', ticker.get('quoteVolume', 0))),
                trades=int(ticker.get('count', ticker.get('trades', 0))),
                timestamp=int(ticker.get('closeTime', ticker.get('time', 0)))
            )

            # Atualiza streams
            self.tickers[symbol] = ticker_obj
            self.markets = self._organize_markets(list(self.tickers.values()))

            # Notifica controller sobre atualização
            if hasattr(self, 'controller') and hasattr(self.controller, 'on_ticker_update'):
                await self.controller.on_ticker_update(self.tickers)
                self.logger.debug(f"✅ Ticker {symbol} processado")

        except Exception as e:
            self.logger.error(f"❌ Erro no tick {symbol}: {str(e)}")
            if self.config.get('DEBUG', False):
                self.logger.error(f"🔍 Detalhes: {str(e.__class__.__name__)}")

    def _organize_markets(self, tickers: List[Ticker]) -> Dict:
        """Organiza tickers por mercado base"""
        markets = {step: [] for step in self.steps}

        for ticker in tickers:
            for base in self.steps:
                symbol = f"{ticker.symbol.base}{ticker.symbol.quote}"
                if symbol.endswith(base):
                    markets[base].append(ticker)
                    break

        return markets

    def get_currency_from_stream(self, stream: Dict, from_cur: str, to_cur: str) -> Optional[Ticker]:
        """Obtém taxa de câmbio entre duas moedas"""
        if not stream or not from_cur or not to_cur:
            return None

        # Tenta encontrar par direto
        symbol = f"{to_cur}{from_cur}"
        currency = stream.get(symbol)

        if currency:
            # Par encontrado na ordem direta
            currency.flipped = False
            currency.rate = float(currency.ask_price)
            currency.step_from = from_cur
            currency.step_to = to_cur
            self.logger.debug(
                f"Par direto encontrado: {symbol} | Taxa: {currency.rate}")
        else:
            # Tenta par inverso
            symbol = f"{from_cur}{to_cur}"
            currency = stream.get(symbol)
            if not currency:
                self.logger.debug(f"Par não encontrado: {from_cur}->{to_cur}")
                return None

            currency.flipped = True
            currency.rate = 1 / float(currency.bid_price)
            currency.step_from = from_cur
            currency.step_to = to_cur
            self.logger.debug(
                f"Par inverso encontrado: {symbol} | Taxa: {currency.rate}")

        return currency

    def get_arbitrage_rate(self, stream: Dict, step1: str, step2: str, step3: str) -> Optional[Dict]:
        """Calcula taxa de arbitragem para um trio de moedas"""
        if not stream or not step1 or not step2 or not step3:
            return None

        self.logger.debug(
            f"Calculando arbitragem: {step1}->{step2}->{step3}->{step1}")

        # Obtém as três conversões necessárias
        a = self.get_currency_from_stream(stream, step1, step2)
        b = self.get_currency_from_stream(stream, step2, step3)
        c = self.get_currency_from_stream(stream, step3, step1)

        if not all([a, b, c]):
            self.logger.debug("Rota incompleta - faltam pares")
            return None

        # Calcula taxa final
        rate = (a.rate * b.rate * c.rate)
        profit = (rate - 1) * 100

        self.logger.debug(f"Taxa final: {rate:.4f} | Lucro: {profit:.2f}%")

        return {
            'a': a,
            'b': b,
            'c': c,
            'rate': rate
        }

    def get_candidates_from_stream_via_path(self, stream: Dict, a_pair: str, b_pair: str) -> List[Dict]:
        """Encontra candidatos de arbitragem via um caminho específico"""
        a_pair = a_pair.upper()
        b_pair = b_pair.upper()

        self.logger.debug(f"🔍 Buscando candidatos via {a_pair}->{b_pair}")

        # Obtém pares dos mercados
        a_pairs = self.markets.get(a_pair, [])
        b_pairs = self.markets.get(b_pair, [])

        if not a_pairs or not b_pairs:
            self.logger.debug(
                f"❌ Mercados não encontrados: {a_pair} ou {b_pair}")
            return []

        # Filtros de volume mínimo (em BTC)
        MIN_VOLUME_BTC = 0.01  # 0.01 BTC
        MIN_TRADES = 10  # Mínimo de trades nas últimas 24h
        MAX_SPREAD = 0.02  # Spread máximo de 2%

        # Mapeia pares do mercado A com filtros
        a_keys = {}
        for pair in a_pairs:
            if (pair.volume > 0 and
                pair.bid_price > 0 and
                pair.ask_price > 0 and
                pair.trades >= MIN_TRADES and
                self._normalize_volume(pair) >= MIN_VOLUME_BTC and
                    (pair.ask_price - pair.bid_price) / pair.ask_price <= MAX_SPREAD):

                symbol = f"{pair.symbol.base}{pair.symbol.quote}"
                key = symbol.replace(a_pair, '')
                a_keys[key] = pair

        # Remove par direto para evitar arbitragem de 1 passo
        if b_pair in a_keys:
            del a_keys[b_pair]

        matches = []

        # Procura matches entre os mercados com filtros aprimorados
        for b_pair_ticker in b_pairs:
            # Valida volume e preços com filtros
            if (b_pair_ticker.volume <= 0 or
                b_pair_ticker.bid_price <= 0 or
                b_pair_ticker.ask_price <= 0 or
                b_pair_ticker.trades < MIN_TRADES or
                self._normalize_volume(b_pair_ticker) < MIN_VOLUME_BTC or
                    (b_pair_ticker.ask_price - b_pair_ticker.bid_price) / b_pair_ticker.ask_price > MAX_SPREAD):
                continue

            symbol = f"{b_pair_ticker.symbol.base}{b_pair_ticker.symbol.quote}"
            key = symbol.replace(b_pair, '')

            if key in a_keys:
                # Encontrou um caminho possível
                step_c = self.get_currency_from_stream(stream, key, a_pair)

                if (step_c and
                    step_c.volume > 0 and
                    step_c.bid_price > 0 and
                    step_c.ask_price > 0 and
                    step_c.trades >= MIN_TRADES and
                    self._normalize_volume(step_c) >= MIN_VOLUME_BTC and
                        (step_c.ask_price - step_c.bid_price) / step_c.ask_price <= MAX_SPREAD):

                    # Calcula taxas e volumes
                    a_ticker = a_keys[key]

                    # Calcula taxas considerando spread
                    a_rate = 1 / \
                        float(a_ticker.ask_price) if a_ticker.flipped else float(
                            a_ticker.bid_price)
                    b_rate = 1 / \
                        float(b_pair_ticker.ask_price) if b_pair_ticker.flipped else float(
                            b_pair_ticker.bid_price)
                    c_rate = 1 / \
                        float(step_c.ask_price) if step_c.flipped else float(
                            step_c.bid_price)

                    # Taxa final considerando spreads
                    rate = a_rate * b_rate * c_rate

                    # Calcula volumes em BTC
                    volumes = [
                        self._normalize_volume(a_ticker),
                        self._normalize_volume(b_pair_ticker),
                        self._normalize_volume(step_c)
                    ]

                    # Calcula spreads
                    spreads = [
                        (a_ticker.ask_price - a_ticker.bid_price) /
                        a_ticker.ask_price,
                        (b_pair_ticker.ask_price - b_pair_ticker.bid_price) /
                        b_pair_ticker.ask_price,
                        (step_c.ask_price - step_c.bid_price) / step_c.ask_price
                    ]

                    # Só adiciona se todos volumes e spreads são válidos
                    if all(v >= MIN_VOLUME_BTC for v in volumes) and all(s <= MAX_SPREAD for s in spreads):
                        match = {
                            'a_step_from': a_pair,
                            'a_step_to': key,
                            'b_step_from': key,
                            'b_step_to': b_pair,
                            'c_step_from': b_pair,
                            'c_step_to': a_pair,
                            'rate': rate,
                            'a_volume': min(volumes),
                            'b_volume': min(volumes),
                            'c_volume': min(volumes),
                            'a_bid': a_ticker.bid_price,
                            'a_ask': a_ticker.ask_price,
                            'b_bid': b_pair_ticker.bid_price,
                            'b_ask': b_pair_ticker.ask_price,
                            'c_bid': step_c.bid_price,
                            'c_ask': step_c.ask_price,
                            'timestamp': datetime.now().isoformat()
                        }

                        # Calcula lucro potencial
                        profit = (rate - 1) * 100

                        if profit > 0.2:  # Filtro inicial de lucro
                            self.logger.debug(
                                f"💫 Oportunidade: {a_pair}->{key}->{b_pair}->{a_pair} | "
                                f"Lucro: {profit:.2f}% | Volume: {min(volumes):.4f} BTC"
                            )
                            matches.append(match)

        if matches:
            self.logger.info(
                f"✨ Encontrados {len(matches)} candidatos viáveis via {a_pair}->{b_pair}")

        return matches

    def _normalize_volume(self, ticker: Ticker) -> float:
        """Normaliza volume para BTC"""
        try:
            # Usa menor entre bid_qty e ask_qty para ser conservador
            qty = min(ticker.bid_qty, ticker.ask_qty)

            if ticker.symbol.quote == 'BTC':
                return qty
            elif ticker.symbol.base == 'BTC':
                return qty * ticker.last_price
            else:
                # Tenta converter para BTC via último preço conhecido
                btc_price = self.tickers.get(f"{ticker.symbol.quote}BTC")
                if btc_price:
                    return qty * ticker.last_price * btc_price.last_price
                return qty * ticker.last_price  # Melhor estimativa possível

        except Exception as e:
            self.logger.error(f"❌ Erro ao normalizar volume: {e}")
            return 0

    def get_dynamic_candidates_from_stream(self, stream: Dict, options: Dict) -> List[Dict]:
        """Busca dinâmica de candidatos de arbitragem"""
        if not stream or not options:
            return []

        self.logger.debug("🔄 Iniciando busca dinâmica de oportunidades...")

        # Lista de moedas base para triangulação
        base_currencies = [
            'BTC', 'ETH', 'BNB', 'USDT',  # Principais
            'BUSD', 'USDC'  # Stablecoins
        ]

        candidates = []
        pairs_checked = 0
        start_time = datetime.now()

        try:
            # Itera sobre combinações de moedas
            for base in base_currencies:
                for quote in base_currencies:
                    if base != quote:
                        # Busca candidatos via este par de moedas
                        new_candidates = self.get_candidates_from_stream_via_path(
                            stream, base, quote
                        )

                        if new_candidates:
                            candidates.extend(new_candidates)
                        pairs_checked += 1

            # Calcula estatísticas
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            pairs_per_second = pairs_checked / duration if duration > 0 else 0

            # Log de resultados
            if candidates:
                self.logger.info(
                    f"\n📊 Resumo da busca:"
                    f"\n   ✓ {len(candidates)} oportunidades encontradas"
                    f"\n   ✓ {pairs_checked} pares verificados"
                    f"\n   ✓ {duration:.1f} segundos"
                    f"\n   ✓ {pairs_per_second:.1f} pares/segundo"
                )

                # Ordena por lucro
                candidates.sort(key=lambda x: x['rate'], reverse=True)

                # Log das melhores oportunidades
                for i, c in enumerate(candidates[:3], 1):
                    profit = (c['rate'] - 1) * 100
                    self.logger.info(
                        f"\n💰 Top {i}:"
                        f"\n   Rota: {c['a_step_from']}->{c['b_step_from']}->{c['c_step_from']}"
                        f"\n   Lucro: {profit:.2f}%"
                        f"\n   Volume: {c['a_volume']:.4f} BTC"
                    )
            else:
                self.logger.debug(
                    f"ℹ️ Nenhuma oportunidade encontrada após verificar {pairs_checked} pares"
                )

        except Exception as e:
            self.logger.error(f"❌ Erro na busca dinâmica: {str(e)}")
            if self.config.get('DEBUG', False):
                self.logger.exception(e)

        return candidates

    async def close(self):
        """Fecha conexões e recursos"""
        try:
            self.logger.info("🔄 Encerrando CurrencyCore...")

            # Fecha conexões aqui

            self.logger.info("✅ CurrencyCore encerrado com sucesso")
        except Exception as e:
            self.logger.error(f"❌ Erro ao encerrar CurrencyCore: {e}")
