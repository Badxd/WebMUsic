cmake_minimum_required(VERSION 3.16)
project(cpp-bot LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(Threads REQUIRED)
find_package(CURL REQUIRED)
find_package(ZLIB REQUIRED)
find_package(mongoc-1.0 REQUIRED)     # libmongoc: MongoDB persistence

# Real voice engine: libntgcalls as a SHARED library (the static build embeds its own libc++abi/BoringSSL, whose symbols
# clash with libstdc++/OpenSSL and break C++ exceptions).
#
# libntgcalls is looked for (header ntgcalls.h + libntgcalls.so) in, in this order:
#   1. the NTGCALLS_INCLUDE_DIR / NTGCALLS_LIBRARY_DIR environment variables (set by the Heroku C++ buildpack when
#      NTGCALLS_URL or NTGCALLS_DIR is configured),
#   2. ${NTGCALLS_DIR}/include and ${NTGCALLS_DIR}/lib (default: third_party/ntgcalls, which the Dockerfile fills).
# If it is found, the real voice engine is enabled automatically. Pass -DWITH_NTGCALLS=OFF to build without it, or
# -DWITH_NTGCALLS=ON to make a missing library a hard configure error instead of a silent voice-less build.
set(NTGCALLS_DIR "${CMAKE_SOURCE_DIR}/third_party/ntgcalls" CACHE PATH "libntgcalls location")
find_path(NTGCALLS_INCLUDE_DIR ntgcalls.h
          HINTS "$ENV{NTGCALLS_INCLUDE_DIR}" "${NTGCALLS_DIR}/include" NO_DEFAULT_PATH)
find_library(NTGCALLS_LIBRARY NAMES libntgcalls.so
             HINTS "$ENV{NTGCALLS_LIBRARY_DIR}" "${NTGCALLS_DIR}/lib" NO_DEFAULT_PATH)
if(NTGCALLS_INCLUDE_DIR AND NTGCALLS_LIBRARY)
  set(_ntg_default ON)
else()
  set(_ntg_default OFF)
endif()
option(WITH_NTGCALLS "link libntgcalls (real voice chats)" ${_ntg_default})
if(WITH_NTGCALLS AND NOT (NTGCALLS_INCLUDE_DIR AND NTGCALLS_LIBRARY))
  message(FATAL_ERROR
    "WITH_NTGCALLS=ON but libntgcalls was not found.\n"
    "  ntgcalls.h   : ${NTGCALLS_INCLUDE_DIR}\n"
    "  libntgcalls.so: ${NTGCALLS_LIBRARY}\n"
    "Provide it under ${NTGCALLS_DIR} (include/ + lib/), or set the NTGCALLS_INCLUDE_DIR / NTGCALLS_LIBRARY_DIR "
    "environment variables, or configure with -DWITH_NTGCALLS=OFF.")
endif()
if(WITH_NTGCALLS)
  message(STATUS "libntgcalls: ${NTGCALLS_LIBRARY} (header dir: ${NTGCALLS_INCLUDE_DIR}) -> real voice engine ENABLED")
else()
  message(WARNING "libntgcalls not found: building WITHOUT the voice engine. The bot will exit at start-up.")
endif()

# bot logic (no Telegram / voice dependency): used by the binary and the tests
file(GLOB_RECURSE BOT_SOURCES CONFIGURE_DEPENDS
     Bad/core/*.cpp Bad/net/*.cpp Bad/cmd/*.cpp Bad/db/*.cpp Bad/i18n/*.cpp Bad/platforms/*.cpp
     Bad/ui/*.cpp Bad/tg/client.cpp Bad/tg/mock_client.cpp Bad/tg/botapi_client.cpp Bad/tg/factory_real.cpp
     Bad/voice/backend.cpp Bad/voice/mock_backend.cpp Bad/voice/assistant.cpp Bad/voice/media_common.cpp
     Bad/voice/media_ntg.cpp Bad/mtp/*.cpp)
add_library(botcore STATIC ${BOT_SOURCES})
target_include_directories(botcore PUBLIC Bad)
target_compile_options(botcore PRIVATE -Wall -Wextra -Wno-unused-parameter)
target_link_libraries(botcore PUBLIC Threads::Threads CURL::libcurl ZLIB::ZLIB mongo::mongoc_shared)
if(WITH_NTGCALLS)
  target_compile_definitions(botcore PUBLIC WITH_NTGCALLS)
  target_include_directories(botcore PUBLIC ${NTGCALLS_INCLUDE_DIR})
  target_link_libraries(botcore PUBLIC ${NTGCALLS_LIBRARY})
endif()

add_executable(cpp-bot Bad/main.cpp)
target_link_libraries(cpp-bot PRIVATE botcore)
if(WITH_NTGCALLS)
  get_filename_component(NTGCALLS_LIBRARY_DIR_RESOLVED "${NTGCALLS_LIBRARY}" DIRECTORY)
  # finds libntgcalls.so in ./lib next to the binary (Docker: /app/lib), in ../third_party/ntgcalls/lib relative to
  # the binary (buildpack layout: /app/build/cpp-bot), or in the build-time location
  set_target_properties(cpp-bot PROPERTIES
    BUILD_RPATH "$ORIGIN/lib;$ORIGIN/../third_party/ntgcalls/lib;${NTGCALLS_LIBRARY_DIR_RESOLVED}"
    INSTALL_RPATH "$ORIGIN/lib")
endif()

# developer tests (not shipped in the deploy repo)
if(EXISTS ${CMAKE_SOURCE_DIR}/tests/test_flow.cpp)
  enable_testing()
  add_executable(bot_tests tests/test_flow.cpp)
  target_link_libraries(bot_tests PRIVATE botcore)
  add_test(NAME flow COMMAND bot_tests WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

  add_executable(adapter_tests tests/test_adapters.cpp)
  target_link_libraries(adapter_tests PRIVATE botcore)
  target_include_directories(adapter_tests PRIVATE tests)
  add_test(NAME adapters COMMAND adapter_tests WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

  add_executable(autoplay_tests tests/test_autoplay.cpp)
  target_link_libraries(autoplay_tests PRIVATE botcore)
  add_test(NAME autoplay COMMAND autoplay_tests WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

  add_executable(mtp_tests tests/test_mtp.cpp)
  target_link_libraries(mtp_tests PRIVATE botcore)
  target_include_directories(mtp_tests PRIVATE tests)
  add_test(NAME mtp COMMAND mtp_tests WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

  add_executable(mongo_tests tests/test_mongo.cpp)
  target_link_libraries(mongo_tests PRIVATE botcore)
  target_include_directories(mongo_tests PRIVATE tests)
  add_test(NAME mongo COMMAND mongo_tests WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

  if(WITH_NTGCALLS)
    add_executable(ntg_smoke tests/ntg_smoke.cpp)
    target_link_libraries(ntg_smoke PRIVATE botcore)
  endif()
endif()
