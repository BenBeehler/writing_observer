'''
This generates dashboards from student data.
'''

import asyncio
import json
import time

import aiohttp

import learning_observer.util as util

import learning_observer.synthetic_student_data as synthetic_student_data

import learning_observer.stream_analytics.helpers as sa_helpers
import learning_observer.kvs as kvs

import learning_observer.paths as paths

import learning_observer.auth
import learning_observer.rosters as rosters


def aggregate_course_data(
        course_id, module_id,
        agg_module, roster,
        default_data={}
):
    '''
    Closure remembers course roster, and redis KVS.

    Reopening connections to redis every few seconds otherwise would
    run us out of file pointers.
    '''
    teacherkvs = kvs.KVS()

    async def rsd():
        '''
        Poll redis for student state. This should be abstracted out into a generic
        aggregator API, much like we have a reducer on the incoming end.
        '''
        students = []
        for student in roster:
            student_data = {
                # We're copying Google's roster format here.
                #
                # It's imperfect, and we may want to change it later, but it seems
                # better than reinventing our own standard.
                #
                # We don't copy verbatim, since we do want to filter down any
                # extra stuff.
                'profile': {
                    'name': {
                        'fullName': student['profile']['name']['fullName']
                    },
                    'photoUrl': student['profile']['photoUrl'],
                    'emailAddress': student['profile']['emailAddress'],
                },
                "courseId": course_id,
                "userId": student['userId'],  # TODO: Encode?
            }
            student_data.update(default_data)

            # TODO/HACK: Only do this for Google data. Make this do the right thing
            # for synthetic data.
            google_id = student['userId']
            if google_id.isnumeric():
                student_id = learning_observer.auth.google_id_to_user_id(google_id)
            else:
                student_id = google_id
            # TODO: Evaluate whether this is a bottleneck.
            #
            # mget is faster than ~50 gets. But some online benchmarks show both taking
            # microseconds, to where it might not matter.
            #
            # For most services (e.g. a SQL database), this would be a huge bottleneck. redis might
            # be fast enough that it doesn't matter? Dunno.
            for sa_module in agg_module['sources']:
                key = sa_helpers.make_key(
                    sa_module,
                    student_id,
                    sa_helpers.KeyStateType.EXTERNAL)
                print(key)
                data = await teacherkvs[key]
                print(data)
                if data is not None:
                    student_data[sa_helpers.fully_qualified_function_name(sa_module)] = data
            cleaner = agg_module.get("cleaner", lambda x: x)
            students.append(cleaner(student_data))

        return students
    return rsd


@learning_observer.auth.teacher
async def ws_course_aggregate_view(request):
    '''
    Handler to aggregate student data, and serve it back to the client
    every half-second to second or so.
    '''
    # print("Serving")
    module_id = request.match_info['module_id']
    course_id = int(request.match_info['course_id'])
    student_id = request.match_info.get('student_id', None)

    # Find the right module
    agg_module = None

    lomlca = learning_observer.module_loader.course_aggregators()
    for m in lomlca:
        if lomlca[m]['short_id'] == module_id:
            # TODO: We should support multiple modules here.
            if agg_module is not None:
                raise aiohttp.web.HTTPNotImplemented(text="Duplicate module: " + m)
            agg_module = lomlca[m]
            default_data = agg_module.get('default-data', {})
    if agg_module is None:
        print("Bad module: ", module_id)
        print("Available modules: ", lomlca)
        raise aiohttp.web.HTTPBadRequest(text="Invalid module: " + m)

    # We need to receive to detect web socket closures.
    ws = aiohttp.web.WebSocketResponse(receive_timeout=0.1)
    await ws.prepare(request)

    roster = await rosters.courseroster(request, course_id)

    # If we're grabbing data for just one student, we filter the
    # roster down.  This pathway ensures we only serve data for
    # students on a class roster.  I'm not sure this API is
    # right. Should we have a different URL? A set of filters? A lot
    # of that is TBD. Once nice property about this is that we have
    # the same data format for 1 student as for a classroom of
    # students.
    if student_id is not None:
        roster = [r for r in roster if r['userId'] == student_id]

    # Grab student list, and deliver to the client
    rsd = aggregate_course_data(
        course_id,
        module_id,
        agg_module,
        roster,
        default_data
    )
    aggregator = agg_module.get('aggregator', lambda x: {})
    while True:
        sd = await rsd()
        data = {
            "student-data": sd   # Per-student list
        }
        data.update(aggregator(sd))
        await ws.send_json(data)
        # This is kind of an awkward block, but aiohttp doesn't detect
        # when sockets close unless they receive data. We try to receive,
        # and wait for an exception or a CLOSE message.
        try:
            if (await ws.receive()).type == aiohttp.WSMsgType.CLOSE:
                print("Socket closed!")
                # By this point, the client is long gone, but we want to
                # return something to avoid confusing middlewares.
                return aiohttp.web.Response(text="This never makes it back....")
        except asyncio.exceptions.TimeoutError:
            # This is the normal code path
            pass
        await asyncio.sleep(0.5)
        # This never gets called, since we return above
        if ws.closed:
            print("Socket closed")
            return aiohttp.web.Response(text="This never makes it back....")


# Obsolete code, but may be repurposed for student dashboards.
#
# aiohttp.web.get('/wsapi/out/', incoming_student_event.outgoing_websocket_handler)

# async def outgoing_websocket_handler(request):
#     '''
#     This pipes analytics back to the browser. It:
#     1. Handles incoming PubSub connections
#     2. Sends it back to the browser

#     TODO: Cleanly handle disconnects
#     '''
#     debug_log('Outgoing analytics web socket connection')
#     ws = aiohttp.web.WebSocketResponse()
#     await ws.prepare(request)
#     pubsub_client = await pubsub.pubsub_receive()
#     debug_log("Awaiting PubSub messages")
#     while True:
#         message = await pubsub_client.receive()
#         debug_log("PubSub event received")
#         log_event.log_event(
#             message, "incoming_pubsub", preencoded=True, timestamp=True
#         )
#         log_event.log_event(
#             message,
#             "outgoing_analytics", preencoded=True, timestamp=True)
#         await ws.send_str(message)
#     await ws.send_str("Done")


# Obsolete code -- we should put this back in after our refactor. Allows us to use
# dummy data
# @learning_observer.auth.teacher
# async def static_student_data_handler(request):
#     '''
#     Populate static / mock-up dashboard with static fake data
#     '''
#     # module_id = request.match_info['module_id']
#     # course_id = int(request.match_info['course_id'])

#     return aiohttp.web.json_response({
#         "new_student_data": json.load(open(paths.static("student_data.js")))
#     })


# @learning_observer.auth.teacher
# async def generated_student_data_handler(request):
#     '''
#     Populate static / mock-up dashboard with static fake data dynamically
#     '''
#     # module_id = request.match_info['module_id']
#     # course_id = int(request.match_info['course_id'])

#     return aiohttp.web.json_response({
#         "new_student_data": synthetic_student_data.synthetic_data()
#     })
