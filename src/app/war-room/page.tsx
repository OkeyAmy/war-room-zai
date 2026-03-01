/**
 * The war room is now a dynamic route at /war-room/[session_id].
 * This redirect ensures any direct visits to /war-room are sent
 * to the landing page where a session must be created first.
 */
import { redirect } from "next/navigation";

export default function WarRoomIndex() {
  redirect("/");
}
