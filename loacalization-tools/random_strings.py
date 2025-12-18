import random
import string
import yaml

def get_random_item(my_list):
    if not my_list:
        return None  # 빈 리스트인 경우 None을 반환
    return random.choice(my_list)

def generate_random_string(length, use_korean=True, use_japanese=True, use_numbers=True, use_special_chars=True, prefix=""):
    # 한국어와 일본어 특수문자 범위 설정
    korean_chars = [chr(i) for i in range(0xAC00, 0xD7A4)]  # Hangul Syllables
    japanese_chars = [chr(i) for i in range(0x3040, 0x30A0)]  # Hiragana & Katakana

    # 숫자 및 특수문자 범위 설정
    numbers = string.digits
    special_chars = string.punctuation

    # 문자 리스트 생성
    chars = ""
    if use_korean:
        chars += ''.join(korean_chars)
    if use_japanese:
        chars += ''.join(japanese_chars)
    if use_numbers:
        chars += numbers
    if use_special_chars:
        chars += special_chars

    # 주어진 길이만큼 무작위 문자 선택
    random_string = prefix + ''.join(random.choice(chars) for _ in range(length))

    return random_string

# 사용자로부터 파일명 입력 받기
input_filename = input("기존 YAML 파일명을 입력하세요: ")
output_filename = input("새로운 YAML 파일명을 입력하세요: ")

# 기존 YAML 파일 로드
with open(input_filename, 'r') as file:
    data = yaml.load(file, Loader=yaml.FullLoader)

random_string = generate_random_string(5, use_korean=True, use_japanese=True, use_numbers=True, use_special_chars=True, prefix="")
type_list = ['table', 'pickpoint', 'charging_station', 'route']
random_type = get_random_item(type_list)

# 새로운 데이터 생성
new_data = {
    random_string: {
            'name': random_string,
            'orientation': {
                'w': 0,
                'x': 0,
                'y': 0,
                'z': 0
            },
            'position': {
                'x': 0,
                'y': 0,
                'z': 0
            },
            'type': random_type
        }
}
print(random_string, random_type)

# data = {
#     'name': 'John Smith',
#     'age': 30,
#     'height': 180.5,
#     'is_student': True,
#     'fruits': ['apple', 'banana', 'cherry'],
#     'address': {
#         'street': '123 Main St',
#         'city': 'Anytown',
#         'zip': '12345'
#     }
# }

# 기존 데이터에 새로운 데이터 추가
data['destinations'].update(new_data)

# 수정된 데이터를 새로운 YAML 파일로 저장
with open(output_filename, 'w') as new_file:
    yaml.dump(data, new_file)
