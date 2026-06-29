Chạy server
python -m uvicorn main:app

Chạy test
pytest test/test_specification.py -v
pytest test/test_compatibility.py -v
python -m pytest test/test_pc_builder_api.py -v
pytest test/test_price_check.py -v
pytest test/test_stream_stop.py -v -s
pytest test/test_restful_chat_api.py -v -s

forward url
ngrok http --url=customer-outskirts-blubber.ngrok-free.dev 8000