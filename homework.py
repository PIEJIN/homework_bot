import logging
import os
import time
import sys
from http import HTTPStatus
import json
import requests
import telegram
from dotenv import load_dotenv


if __name__ == '__main__':
    load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s, %(levelname)s, %(message)s',
    level=logging.DEBUG
)


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
UNIX_MOUNTH = 2629746
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет доступность переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Отправка сообщения')
    except Exception as error:
        logger.error(f'Ошибка отправки сообщения. {error}')


def get_api_answer(timestamp):
    """Запрос к единственному эндпоинту API-сервиса.
    Возвращает ответ API, приведя его из формата JSON к типам данных Python.
    """
    try:
        homework_statuses = requests.get(
            ENDPOINT, headers=HEADERS, params=timestamp
        )
        if homework_statuses.status_code != HTTPStatus.OK:
            raise Exception(
                logger.error(f'Ошибка {homework_statuses.status_code}')
            )
        return homework_statuses.json()
    except requests.RequestException:
        pass
    except json.decoder.JSONDecodeError:
        logger.error('Ошибка при декодировании')


def check_response(response: dict) -> bool:
    """Проверяет ответ API."""
    if 'current_date' not in response or 'homeworks' not in response:
        logger.error('Отсутствуют ожидаемые ключи')
        raise TypeError(
            'API возвращает некоректную информацию'
        )

    if not isinstance(response, dict):
        raise TypeError('API возвращает  не dict.')
    if not bool(response['homeworks']):
        raise KeyError(
            'Домашних работ нет'
        )
    if not isinstance(response['homeworks'], list):
        raise TypeError('Список домашних работ не list')

    if response['homeworks'][0]['status'] not in HOMEWORK_VERDICTS:
        logger.error('Неожиданный статус домашней работы')

    if (response == {
        "error": {"error": "Wrong from_date format"},
        "code": "UnknownError"
    }
    ):
        logger.error('Недоступность эндпоинта')
    return True


def parse_status(homework: dict) -> str:
    """Возвращает подготовленную для отправки в Telegram строку.
    Т.е один из вердиктов словаря HOMEWORK_VERDICTS.
    """
    if 'homeworks' in homework:
        last_homework = homework['homeworks'][0]
    elif 'homework_name' in homework:
        last_homework = homework
    else:
        raise Exception('Неверный формат словаря')

    homework_name = last_homework.get('homework_name')
    status = last_homework.get('status')
    verdict = HOMEWORK_VERDICTS.get(status)

    if verdict is None:
        raise KeyError('Ошибка со статусом проверки')

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logging.critical(
            'Отсутствие обязательных переменных окружения'
        )
        sys.exit()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    actual_result = None
    prev_result = None
    payload = {'from_date': int(time.time() - UNIX_MOUNTH)}
    while True:
        try:
            response = get_api_answer(payload)
            if check_response(response):
                prev_result = parse_status(response)
                payload = {'from_date': response['current_date'] - UNIX_MOUNTH}

                if actual_result is None:
                    actual_result = prev_result
                    send_message(bot, prev_result)

                if actual_result != prev_result:
                    actual_result = prev_result
                    send_message(bot, actual_result)

                if actual_result == prev_result:
                    logging.debug('Статус домашней работы не изменился')

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
            logging.info('Отправка сообщения об ошибке')

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
