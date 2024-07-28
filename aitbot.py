import pandas as pd
import numpy as np
from binance.client import Client
from binance.enums import *
from talib import EMA, SMA
import time
from binance.exceptions import BinanceAPIException, BinanceOrderException

# Define your API keys here
api_key = "yourkey"
api_secret = "yoursecret"

# Create the Binance client
client = Client(api_key, api_secret)

# Define your trading parameters
symbol = 'BTCUSDT'
interval = Client.KLINE_INTERVAL_1MINUTE
ema_length = 30
sma_length = 10
amount_usdt = 3  # replace with the amount of USDT you want to spend per order

def get_precision(symbol):
    info = client.futures_exchange_info()
    symbol_info = next((s for s in info['symbols'] if s['symbol'] == symbol), None)
    if symbol_info is None:
        raise ValueError(f"Symbol {symbol} not found.")
    filters = symbol_info['filters']
    lot_size_filter = next((f for f in filters if f['filterType'] == 'LOT_SIZE'), None)
    if lot_size_filter is None:
        raise ValueError(f"LOT_SIZE filter not found for symbol {symbol}.")
    step_size = float(lot_size_filter['stepSize'])
    precision = int(round(-np.log10(step_size)))
    #min_precision = 2  # Comment this line out
    return precision  # just return the calculated precision

precision = get_precision(symbol)


def fetch_data(symbol, interval):
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=1000)
    data = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    data['close'] = pd.to_numeric(data['close'])
    data['ema'] = EMA(data['close'], timeperiod=ema_length)
    data['sma'] = SMA(data['close'], timeperiod=sma_length)
    data['long_signal'] = np.where(data['ema'] > data['sma'], 1, 0)
    data['short_signal'] = np.where(data['ema'] < data['sma'], 1, 0)
    return data

def place_order(signal):
    current_price = client.futures_mark_price(symbol=symbol)['markPrice']
    
    info = client.futures_exchange_info()
    symbol_info = next((s for s in info['symbols'] if s['symbol'] == symbol), None)
    lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
    min_qty = float(lot_size_filter['minQty'])
    max_qty = float(lot_size_filter['maxQty'])
    step_size = float(lot_size_filter['stepSize'])

    quantity = round((amount_usdt * 35) / float(current_price), precision)
    if quantity < min_qty:
        print(f'Quantity {quantity} is less than the minimum quantity {min_qty}. Increasing the quantity to {min_qty}.')
        quantity = min_qty
    elif quantity > max_qty:
        print(f'Quantity {quantity} is more than the maximum quantity {max_qty}. Decreasing the quantity to {max_qty}.')
        quantity = max_qty
    else:
        quantity = round(quantity / step_size) * step_size  # adjust the quantity to a multiple of the step size
    
    try:
        order = client.futures_create_order(
            symbol=symbol,
            side=signal,
            type=ORDER_TYPE_MARKET,
            quantity=quantity
        )
        print(f'Successfully placed {signal} order: {order}')
    except BinanceAPIException as e:
        print(f'Failed to place {signal} order: {e}')
    except BinanceOrderException as e:
        print(f'Order exception: {e}')
    except Exception as e:
        print(f'Unexpected exception: {e}')

# Place orders
while True:
    print("Fetching data...")
    # Update data
    data = fetch_data(symbol, interval)
    if pd.notna(data.iloc[-1]['ema']) and pd.notna(data.iloc[-1]['sma']):
        open_orders = client.futures_get_open_orders(symbol=symbol)
        if len(open_orders) == 0:  # only proceed if there are no open orders
            if data.iloc[-1]['long_signal'] == 1 and data.iloc[-2]['long_signal'] == 0:
                # Place a buy order
                print("EMA crossed above SMA. Placing a buy order based on the signal.")
                place_order(SIDE_BUY)
            elif data.iloc[-1]['short_signal'] == 1 and data.iloc[-2]['short_signal'] == 0:
                # Place a sell order
                print("EMA crossed below SMA. Placing a sell order based on the signal.")
                place_order(SIDE_SELL)
        else:
            print("Open orders exist. Not placing new order.")
    else:
        print("No valid EMA/SMA data for this data point.")
    time.sleep(60)
